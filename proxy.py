import asyncio, urllib.parse, httpx, time, random
from fastapi import FastAPI, Response, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List

app = FastAPI(title="OpenWave Unified API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    expose_headers=["Content-Type", "Accept-Ranges", "Content-Length"]
)

# ═══════════════════════════════════════════
# 🔑 YOUR KEYS (Get a free Giphy key at developers.giphy.com)
# ═══════════════════════════════════════════
AUDIUS_TOKEN = "YOUR_AUDIUS_BEARER_TOKEN_HERE"
JAMENDO_CLIENT_ID = "f0a8f09d"
GIPHY_API_KEY = "U7JvQ69E25y302BV0dIV6dhfVWIITnCl" # <-- Get this free key

# ═══════════════════════════════════════════
# 📊 STATE
# ═══════════════════════════════════════════
users_db: Dict[str, dict] = {}
community_messages = [{"user": "System", "text": "Welcome to OpenWave!", "time": "12:00"}]
video_feed_cache = {"data": [], "time": 0}

# ═══════════════════════════════════════════
# 🎵 MUSIC ENDPOINTS (From your original)
# ═══════════════════════════════════════════
@app.get("/api/audius/trending")
async def audius_trending():
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://api.audius.co/v1/tracks/trending?app_name=OPENWAVE",
                headers={"Authorization": f"Bearer {AUDIUS_TOKEN}"}, timeout=10.0)
            return res.json()
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
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("https://api.jamendo.com/v3.0/tracks/",
                params={"client_id": JAMENDO_CLIENT_ID, "format": "json", "limit": 20, "audioformat": "mp32"}, timeout=10.0)
            return res.json()
    except: return {"results": []}

@app.get("/api/my_music")
async def get_my_music():
    return {"tracks": [
        {"id": "my_1", "title": "Katalia Jazziq x Thesiix", "artist": "My Upload",
         "artwork": "https://res.cloudinary.com/rcp3saw5/video/upload/v1793275914/Katalia_Jazziq_x_Thesiix.jpg",
         "streamUrl": "https://res.cloudinary.com/rcp3saw5/video/upload/v1793275914/Katalia_Jazziq_x_Thesiix.mp4"}
    ]}

# ═══════════════════════════════════════════
# 🎬 VIDEO FEED (Using GIPHY for legal funny content)
# ═══════════════════════════════════════════
@app.get("/api/video/feed")
async def video_feed():
    global video_feed_cache
    # Cache for 5 minutes to save API limits
    if time.time() - video_feed_cache["time"] < 300 and video_feed_cache["data"]:
        return {"videos": video_feed_cache["data"]}

    if GIPHY_API_KEY == "YOUR_GIPHY_API_KEY_HERE":
        return {"videos": [], "error": "Add your GIPHY_API_KEY to proxy.py"}

    try:
        async with httpx.AsyncClient() as client:
            # Fetch "funny" GIFs from Giphy's official API
            res = await client.get("https://api.giphy.com/v1/gifs/search",
                params={"api_key": GIPHY_API_KEY, "q": "funny", "limit": 20, "rating": "g"}, timeout=10.0)
            data = res.json()
            
            videos = []
            for gif in data.get("data", []):
                videos.append({
                    "id": gif["id"],
                    "title": gif["title"] or "Funny Clip",
                    "creator": gif["username"] or "Giphy",
                    "category": "Comedy",
                    "views": f"{random.randint(10, 500)}K views",
                    "age": "Just now",
                    "duration": "GIF",
                    "image": gif["images"]["fixed_height"]["url"],
                    "videoUrl": gif["images"]["original_mp4"]["mp4"] if "original_mp4" in gif["images"] else gif["images"]["original"]["url"],
                    "description": "Funny moment from Giphy."
                })
            
            video_feed_cache = {"data": videos, "time": time.time()}
            return {"videos": videos}
    except Exception as e:
        return {"videos": [], "error": str(e)}

# ═══════════════════════════════════════════
# 💬 COMMUNITY (Unified)
# ═══════════════════════════════════════════
class ChatMessage(BaseModel):
    user: str
    text: str
    time: str

@app.get("/api/community/chat")
async def get_chat():
    return {"messages": community_messages[-50:]}

@app.post("/api/community/chat")
async def post_chat(msg: ChatMessage):
    community_messages.append({"user": msg.user, "text": msg.text, "time": msg.time})
    return {"status": "success"}

# ═══════════════════════════════════════════
# 🩺 HEALTH
# ═══════════════════════════════════════════
@app.get("/api/health")
async def health():
    return {"status": "ok", "videos_cached": len(video_feed_cache["data"])}
