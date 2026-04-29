"""
VOXA Backend — Main Entry Point
Initializes FastAPI app, mounts routers, and manages service startup.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from pathlib import Path

from config import HOST, PORT, CORS_ORIGINS, DATA_DIR, WHISPER_MODEL
from services.data_service import init_data_service
from services.stt_service import init_stt_service
from routers import health, speech, chat, query, history, auth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("voxa.main")

app = FastAPI(
    title="VOXA — Voice-Enabled AI Automotive Assistant",
    description="Backend API for VOXA, serving automotive plant data insights via voice/text.",
    version="1.0.0",
)

# ── Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Service Initialization ──
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing VOXA backend services...")
    
    # Initialize Data Service (DuckDB + Excel)
    try:
        init_data_service(DATA_DIR)
        logger.info("Data service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize data service: {e}")
        # We don't exit here to allow other services to start, 
        # but queries will fail.
    
    # Initialize STT Service (Whisper)
    try:
        # Note: This might be slow on first run as it downloads the model
        init_stt_service(WHISPER_MODEL)
        logger.info(f"STT service initialized with model: {WHISPER_MODEL}")
    except Exception as e:
        logger.error(f"Failed to initialize STT service: {e}")

from fastapi.staticfiles import StaticFiles

# Create uploads directory if it doesn't exist
uploads_dir = DATA_DIR / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)

# ── Router Mounting ──
# Prefix all routes with /api as expected by the frontend
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(speech.router, prefix="/api", tags=["Speech"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(query.router, prefix="/api", tags=["Query"])
app.include_router(history.router, prefix="/api", tags=["History"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])

# Serve static files from the uploads directory
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

@app.get("/")
async def root():
    return {
        "message": "VOXA Backend is running",
        "docs": "/docs",
        "health": "/api/health"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
