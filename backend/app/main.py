from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

from app.routers import image, history, video, watchlist, alerts_ws   # ← added alerts_ws
from app.database import engine
from app.models import Base
from app.config import COUNTRY_CONFIG

# ---------- DB ----------
Base.metadata.create_all(bind=engine)

# ---------- PATHS ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
IMAGE_DIR  = os.path.join(UPLOAD_DIR, "images")
VIDEO_DIR  = os.path.join(UPLOAD_DIR, "videos")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# ---------- APP ----------
app = FastAPI(title="RoadEye LPR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://road-eye-lpr.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- STATIC ----------
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ---------- ROUTERS ----------
app.include_router(image.router,    prefix="/detect",    tags=["Detection"])
app.include_router(video.router,    prefix="/ws",        tags=["WebSocket"])
app.include_router(alerts_ws.router,prefix="/ws",        tags=["WebSocket"])  # ← /ws/alerts
app.include_router(history.router,  prefix="/history",   tags=["History"])
app.include_router(watchlist.router,prefix="/watchlist", tags=["Watchlist"])

# ---------- COUNTRY CONFIG ----------
class CountryConfigRequest(BaseModel):
    country: str

@app.post("/config/country")
def set_country(cfg: CountryConfigRequest):
    COUNTRY_CONFIG.set(cfg.country)
    return {"status": "ok", "country": COUNTRY_CONFIG.get()}

@app.get("/config/country")
def get_country():
    return {"country": COUNTRY_CONFIG.get()}

# ---------- HEALTH ----------
@app.get("/")
async def root():
    return {
        "message":  "RoadEye LPR API",
        "version":  "1.0.0",
        "country":  COUNTRY_CONFIG.get(),
        "endpoints": {
            "image_detection":  "/detect/image",
            "video_stream":     "/ws/video",
            "webcam_stream":    "/ws/webcam",
            "alert_push":       "/ws/alerts",
            "history":          "/history",
            "watchlist":        "/watchlist",
        },
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}