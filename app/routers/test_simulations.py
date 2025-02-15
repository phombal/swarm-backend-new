from typing import Dict, List, Optional
from datetime import datetime
import asyncio
import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Import local modules
from app.services.twilio_service import TwilioService
from app.services.test_runner import TestRunner
from app.models.simulation import SimulationCreate, SimulationResponse, SimulationStatus
from app.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/create", response_model=SimulationResponse)
async def create_simulation(
    simulation: SimulationCreate,
    background_tasks: BackgroundTasks
):
    """
    Create a new test simulation with specified parameters.
    """
    try:
        db = await get_db()
        # Create simulation record in database
        simulation_id = await db.create_simulation(
            user_id="default",  # Using a default user ID since we removed auth
            target_phone=simulation.target_phone,
            concurrent_calls=simulation.concurrent_calls,
            scenario=simulation.scenario
        )
        
        # Initialize test runner
        test_runner = TestRunner(
            simulation_id=simulation_id,
            target_phone=simulation.target_phone,
            concurrent_calls=simulation.concurrent_calls,
            scenario=simulation.scenario
        )
        
        # Start simulation in background
        background_tasks.add_task(test_runner.run_simulation)
        
        return SimulationResponse(
            id=simulation_id,
            status="initiated",
            message="Test simulation started successfully"
        )
    
    except Exception as e:
        logger.error(f"Error creating simulation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{simulation_id}", response_model=SimulationStatus)
async def get_simulation_status(simulation_id: str):
    """
    Get the current status of a test simulation.
    """
    try:
        db = await get_db()
        status = await db.get_simulation_status(simulation_id)
        if not status:
            raise HTTPException(status_code=404, detail="Simulation not found")
        return status
    except Exception as e:
        logger.error(f"Error getting simulation status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop/{simulation_id}")
async def stop_simulation(simulation_id: str):
    """
    Stop an ongoing test simulation.
    """
    try:
        db = await get_db()
        await db.update_simulation_status(simulation_id, "stopped")
        return {"message": "Simulation stopped successfully"}
    except Exception as e:
        logger.error(f"Error stopping simulation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/results/{simulation_id}")
async def get_simulation_results(simulation_id: str):
    """
    Get detailed results of a completed test simulation.
    """
    try:
        db = await get_db()
        results = await db.get_simulation_results(simulation_id)
        if not results:
            raise HTTPException(status_code=404, detail="Simulation results not found")
        return results
    except Exception as e:
        logger.error(f"Error getting simulation results: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 