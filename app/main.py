from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Call Platform")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import router after FastAPI initialization
from app.voice_router import router as voice_router

# Include router
app.include_router(voice_router, tags=["Voice"])

@app.on_event("startup")
async def startup_event():
    from app.database import init_db
    await init_db()

@app.get("/")
async def root():
    return {"message": "Voice Call Platform is running"} 