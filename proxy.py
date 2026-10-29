import asyncio
import urllib.parse
import httpx
from fastapi import FastAPI, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Accept-Ranges", "Content-Length"]
)

# ==========================================
# 🔑 YOUR API KEYS
# ==========================================
AUDIUS_TOKEN = "bGVRhRUXM29ePJtL1RVmefUOEl1C9EXhRUc5ZY1ER68=" # <-- PASTE YOUR AUDIUS TOKEN HERE
JAMENDO_CLIENT_ID = "f0a8f09d" 

# ==========================================
# 🎵 YOUR PERSONAL MUSIC (CLOUDINARY)
# ==========================================
MY_MUSIC = [
    {
        "id": "my_1",
        "title": "Katalia Jazziq x Thesiix",
        "artist": "My Upload",
        "artwork": "https://res.cloudinary.com/rcp3saw5/video/upload/v1793275914/Katalia_Jazziq_x_Thesiix.jpg", 
        "streamUrl": "https://res.cloudinary.com/rcp3saw5/video/upload/v1793275914/Katalia_Jazziq_x_Thesiix.mp4"
    }
]

@app.get("/api/my_music")
async def get_my_music():
    return {"tracks": MY_MUSIC}

# ==========================================
# 🎵 AUDIO & SEARCH ENDPOINTS
# ==========================================
@app.get("/api/audius/trending")
async def get_audius_trending():
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://api.audius.co/v1/tracks/trending?app_name=OPENWAVE", 
                headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"}, 
                timeout=10.0
            )
            return res.json()
    except: return {"data": []}

@app.get("/api/audius/stream/{track_id}")
async def stream_audius(track_id: str):
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api.audius.co/v1/tracks/{track_id}/stream?app_name=OPENWAVE", 
                headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"}, 
                follow_redirects=True, 
                timeout=15.0
            )
            return Response(
                content=res.content, 
                media_type="audio/mpeg", 
                headers={"Accept-Ranges": "bytes"}
            )
    except: return Response(status_code=500)

@app.get("/api/jamendo/trending")
async def get_jamendo_trending():
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://api.jamendo.com/v3.0/tracks/", 
                params={
                    "client_id": JAMENDO_CLIENT_ID, 
                    "format": "json", 
                    "limit": 20, 
                    "audioformat": "mp32"
                }, 
                timeout=10.0
            )
            return res.json()
    except: return {"results": []}

@app.get("/api/search")
async def search_tracks(q: str = Query(..., min_length=1)):
    try:
        async with httpx.AsyncClient() as client:
            a_task = client.get(
                f"https://api.audius.co/v1/tracks/search?query={urllib.parse.quote(q)}&app_name=OPENWAVE", 
                headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"}
            )
            j_task = client.get(
                "https://api.jamendo.com/v3.0/tracks/", 
                params={
                    "client_id": JAMENDO_CLIENT_ID, 
                    "format": "json", 
                    "limit": 20, 
                    "search": q, 
                    "audioformat": "mp32"
                }
            )
            a_res, j_res = await asyncio.gather(a_task, j_task)
            return {
                "audius": a_res.json().get("data", []), 
                "jamendo": j_res.json().get("results", [])
            }
    except: return {"audius": [], "jamendo": []}

@app.get("/api/lyrics")
async def get_lyrics(artist: str, title: str):
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
            )
            if res.status_code == 200: return res.json()
            return {"lyrics": "Lyrics not found."}
    except: return {"lyrics": "Lyrics service unavailable."}

# ==========================================
# 🌐 COMMUNITY HUB
# ==========================================
community_messages = [{"user": "System", "text": "Welcome to OpenWave!", "time": "12:00"}]

class ChatMessage(BaseModel):
    user: str
    text: str
    time: str

@app.get("/api/community/playlists")
async def get_community_playlists():
    return {
        "playlists": [
            {"id": "1", "name": "Late Night Coding", "author": "Alex", "plays": 342, "tracks_count": 25, "color": "#7C5CFF"},
            {"id": "2", "name": "Gym Hype 2024", "author": "Sarah", "plays": 1205, "tracks_count": 50, "color": "#FF5C7A"}
        ]
    }

@app.get("/api/community/chat")
async def get_community_chat():
    return {"messages": community_messages[-50:]}

@app.post("/api/community/chat")
async def post_community_chat(msg: ChatMessage):
    community_messages.append({
        "user": msg.user,
        "text": msg.text,
        "time": msg.time
    })
    return {"status": "success"}
