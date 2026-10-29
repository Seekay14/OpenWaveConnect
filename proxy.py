import asyncio, urllib.parse, httpx, time, jwt, hashlib, random, json
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import FastAPI, Response, Query, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List

app = FastAPI(title="OpenWave API v2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    expose_headers=["Content-Type", "Accept-Ranges", "Content-Length"]
)

# ═══════════════════════════════════════════
# 🔑 KEYS
# ═══════════════════════════════════════════
AUDIUS_TOKEN = "PASTE_YOUR_AUDIUS_TOKEN_HERE"
JAMENDO_CLIENT_ID = "f0a8f09d"
JWT_SECRET = "CHANGE_THIS_TO_A_RANDOM_STRING_IN_PRODUCTION"

# ═══════════════════════════════════════════
# 📊 IN-MEMORY STATE (upgrade to PostgreSQL later)
# ═══════════════════════════════════════════
users_db: Dict[str, dict] = {}
ratings_db: Dict[str, dict] = defaultdict(dict)
rate_limits: Dict[str, list] = defaultdict(list)
cache: Dict[str, dict] = {}
active_sockets: List[WebSocket] = []

# ═══════════════════════════════════════════
# 🛡️ RATE LIMITING (Pillar 9)
# ═══════════════════════════════════════════
def rate_check(ip: str, limit: int = 60, window: int = 60) -> bool:
    now = time.time()
    rate_limits[ip] = [t for t in rate_limits[ip] if now - t < window]
    if len(rate_limits[ip]) >= limit: return False
    rate_limits[ip].append(now)
    return True

# ═══════════════════════════════════════════
# 🎵 CACHING (Pillar 9)
# ═══════════════════════════════════════════
def cache_get(key: str):
    if key in cache and time.time() - cache[key]["t"] < 300:
        return cache[key]["v"]
    return None

def cache_set(key: str, value):
    cache[key] = {"v": value, "t": time.time()}

# ═══════════════════════════════════════════
# 🩺 HEALTH CHECK (Pillar 9)
# ═══════════════════════════════════════════
@app.get("/api/health")
async def health():
    return {"status": "ok", "uptime": time.time(), "users": len(users_db), "cached": len(cache)}

# ═══════════════════════════════════════════
# 👤 AUTHENTICATION (Pillar 9 - JWT)
# ═══════════════════════════════════════════
class UserAuth(BaseModel):
    name: str
    username: str

def make_token(username: str) -> str:
    return jwt.encode({"sub": username, "exp": datetime.utcnow() + timedelta(days=30)}, JWT_SECRET, algorithm="HS256")

@app.post("/api/auth/signup")
async def signup(user: UserAuth):
    if user.username in users_db:
        raise HTTPException(400, "Username taken")
    users_db[user.username] = {
        "name": user.name, "username": user.username,
        "joined": datetime.utcnow().isoformat(),
        "stats": {"totalMinutes": 0, "topArtists": {}, "history": []},
        "following": [], "followers": []
    }
    token = make_token(user.username)
    return {"status": "success", "token": token, "user": users_db[user.username]}

@app.post("/api/auth/login")
async def login(user: UserAuth):
    if user.username not in users_db:
        raise HTTPException(404, "User not found")
    token = make_token(user.username)
    return {"status": "success", "token": token, "user": users_db[user.username]}

# ═══════════════════════════════════════════
# 🎵 MUSIC STREAMING (Pillar 1)
# ═══════════════════════════════════════════
MY_MUSIC = [
    {"id": "my_1", "title": "Katalia Jazziq x Thesiix", "artist": "My Upload",
     "artwork": "https://res.cloudinary.com/rcp3saw5/video/upload/v1793275914/Katalia_Jazziq_x_Thesiix.jpg",
     "streamUrl": "https://res.cloudinary.com/rcp3saw5/video/upload/v1793275914/Katalia_Jazziq_x_Thesiix.mp4"}
]

@app.get("/api/my_music")
async def get_my_music():
    return {"tracks": MY_MUSIC}

@app.get("/api/audius/trending")
async def audius_trending():
    cached = cache_get("audius_trend")
    if cached: return cached
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://api.audius.co/v1/tracks/trending?app_name=OPENWAVE",
                headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"}, timeout=10.0)
            data = res.json()
            cache_set("audius_trend", data)
            return data
    except: return {"data": []}

@app.get("/api/audius/stream/{track_id}")
async def audius_stream(track_id: str):
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"https://api.audius.co/v1/tracks/{track_id}/stream?app_name=OPENWAVE",
                headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"}, follow_redirects=True, timeout=15.0)
            return Response(content=res.content, media_type="audio/mpeg", headers={"Accept-Ranges": "bytes"})
    except: return Response(status_code=500)

@app.get("/api/jamendo/trending")
async def jamendo_trending():
    cached = cache_get("jamendo_trend")
    if cached: return cached
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://api.jamendo.com/v3.0/tracks/",
                params={"client_id": JAMENDO_CLIENT_ID, "format": "json", "limit": 20, "audioformat": "mp32"}, timeout=10.0)
            data = res.json()
            cache_set("jamendo_trend", data)
            return data
    except: return {"results": []}

@app.get("/api/search")
async def search(q: str = Query(..., min_length=1)):
    cached = cache_get(f"search_{q}")
    if cached: return cached
    try:
        async with httpx.AsyncClient() as client:
            a = client.get(f"https://api.audius.co/v1/tracks/search?query={urllib.parse.quote(q)}&app_name=OPENWAVE",
                headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"})
            j = client.get("https://api.jamendo.com/v3.0/tracks/",
                params={"client_id": JAMENDO_CLIENT_ID, "format": "json", "limit": 20, "search": q, "audioformat": "mp32"})
            a_res, j_res = await asyncio.gather(a, j)
            result = {"audius": a_res.json().get("data", []), "jamendo": j_res.json().get("results", [])}
            cache_set(f"search_{q}", result)
            return result
    except: return {"audius": [], "jamendo": []}

# ═══════════════════════════════════════════
# 🤖 DISCOVER WEEKLY (Pillar 2)
# ═══════════════════════════════════════════
@app.get("/api/discover/{username}")
async def discover(username: str):
    if username not in users_db:
        raise HTTPException(404, "User not found")
    top = sorted(users_db[username]["stats"]["topArtists"].items(), key=lambda x: -x[1])[:3]
    if not top:
        return {"tracks": []}
    tracks = []
    for artist, _ in top:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"https://api.audius.co/v1/tracks/search?query={urllib.parse.quote(artist)}&app_name=OPENWAVE",
                    headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"}, timeout=5.0)
                tracks += res.json().get("data", [])[:5]
        except: pass
    return {"tracks": tracks[:20]}

# ═══════════════════════════════════════════
# ⭐ RATINGS (Pillar 7)
# ═══════════════════════════════════════════
class Rating(BaseModel):
    track_id: str
    stars: int

@app.post("/api/rate/{username}")
async def rate(username: str, r: Rating):
    if r.stars < 1 or r.stars > 5:
        raise HTTPException(400, "Stars must be 1-5")
    ratings_db[username][r.track_id] = r.stars
    return {"status": "ok"}

@app.get("/api/ratings/{username}")
async def get_ratings(username: str):
    return {"ratings": ratings_db.get(username, {})}

# ═══════════════════════════════════════════
# 🎤 LYRICS (Pillar 8)
# ═══════════════════════════════════════════
@app.get("/api/lyrics")
async def lyrics(artist: str, title: str):
    cached = cache_get(f"lyr_{artist}_{title}")
    if cached: return cached
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}")
            data = res.json() if res.status_code == 200 else {"lyrics": "Not found"}
            cache_set(f"lyr_{artist}_{title}", data)
            return data
    except: return {"lyrics": "Service unavailable"}

# ═══════════════════════════════════════════
# 💬 COMMUNITY CHAT (Pillar 3)
# ═══════════════════════════════════════════
community_messages = [{"user": "System", "text": "Welcome!", "time": "12:00"}]

class ChatMessage(BaseModel):
    user: str
    text: str
    time: str

@app.get("/api/community/playlists")
async def playlists():
    return {"playlists": [
        {"id": "1", "name": "Late Night Coding", "author": "Alex", "plays": 342, "tracks_count": 25, "color": "#7C5CFF"},
        {"id": "2", "name": "Gym Hype", "author": "Sarah", "plays": 1205, "tracks_count": 50, "color": "#FF5C7A"}
    ]}

@app.get("/api/community/chat")
async def get_chat():
    return {"messages": community_messages[-50:]}

@app.post("/api/community/chat")
async def post_chat(msg: ChatMessage):
    community_messages.append({"user": msg.user, "text": msg.text, "time": msg.time})
    # Broadcast to all WebSocket listeners (Pillar 3 - real-time)
    dead = []
    for ws in active_sockets:
        try: await ws.send_json({"type": "chat", "data": msg.dict()})
        except: dead.append(ws)
    for ws in dead: active_sockets.remove(ws)
    return {"status": "success"}

# ═══════════════════════════════════════════
# 🔌 WEBSOCKET (Pillar 3 - Listening Parties)
# ═══════════════════════════════════════════
@app.websocket("/ws/{username}")
async def ws_endpoint(ws: WebSocket, username: str):
    await ws.accept()
    active_sockets.append(ws)
    try:
        while True:
            msg = await ws.receive_json()
            # Broadcast "now playing" to all
            for s in active_sockets:
                try: await s.send_json({"type": "sync", "user": username, "data": msg})
                except: pass
    except WebSocketDisconnect:
        if ws in active_sockets: active_sockets.remove(ws)
