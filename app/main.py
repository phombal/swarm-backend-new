from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Stratify Testing Platform")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routers after FastAPI initialization
from app.routers import test_simulations

# Include routers
app.include_router(test_simulations.router, prefix="/simulations", tags=["Test Simulations"])

@app.on_event("startup")
async def startup_event():
    from app.database import init_db
    await init_db()

@app.get("/")
async def root():
    return {"message": "Welcome to Stratify Testing Platform"} 