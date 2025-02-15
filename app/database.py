from typing import Dict, Optional
import logging
from datetime import datetime, UTC
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

try:
    supabase: Client = create_client(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY
    )
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {str(e)}")
    raise

async def init_db():
    """Initialize database connection."""
    try:
        # Test the connection
        supabase.table("simulations").select("count", count="exact").execute()
        logger.info("Database connection initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database connection: {str(e)}")
        raise

async def get_db():
    """Get database connection."""
    return supabase

async def create_simulation(user_id: str, target_phone: str, concurrent_calls: int, scenario: Dict) -> str:
    """Create a new simulation record."""
    try:
        result = supabase.table("simulations").insert({
            "user_id": user_id,
            "target_phone": target_phone,
            "concurrent_calls": concurrent_calls,
            "scenario": scenario,
            "status": "initiated",
            "start_time": datetime.now(UTC).isoformat()
        }).execute()
        
        return result.data[0]["id"]
    except Exception as e:
        logger.error(f"Error creating simulation: {str(e)}")
        raise

async def create_call_record(simulation_id: str, call_sid: str) -> str:
    """Create a new call record."""
    try:
        result = supabase.table("call_records").insert({
            "simulation_id": simulation_id,
            "call_sid": call_sid,
            "status": "initiated",
            "created_at": datetime.now(UTC).isoformat()
        }).execute()
        
        return result.data[0]["id"]
    except Exception as e:
        logger.error(f"Error creating call record: {str(e)}")
        raise

async def update_simulation_status(simulation_id: str, status: str, error: Optional[str] = None):
    """Update simulation status."""
    try:
        update_data = {
            "status": status,
            "updated_at": datetime.now(UTC).isoformat()
        }
        
        if status in ["completed", "failed"]:
            update_data["end_time"] = datetime.now(UTC).isoformat()
        
        if error:
            update_data["error"] = error
            
        supabase.table("simulations").update(update_data).eq("id", simulation_id).execute()
    except Exception as e:
        logger.error(f"Error updating simulation status: {str(e)}")
        raise

async def get_simulation_status(simulation_id: str):
    """Get simulation status."""
    try:
        result = supabase.table("simulations").select("*").eq("id", simulation_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error getting simulation status: {str(e)}")
        raise

async def get_simulation_results(simulation_id: str):
    """Get simulation results including all call records."""
    try:
        simulation = supabase.table("simulations").select("*").eq("id", simulation_id).execute()
        calls = supabase.table("call_records").select("*").eq("simulation_id", simulation_id).execute()
        
        if not simulation.data:
            return None
            
        return {
            **simulation.data[0],
            "calls": calls.data
        }
    except Exception as e:
        logger.error(f"Error getting simulation results: {str(e)}")
        raise

async def update_call_transcript(simulation_id: str, call_sid: str, transcript: list):
    """Update call transcript."""
    try:
        # First ensure the call record exists
        existing_call = supabase.table("call_records").select("id").eq("simulation_id", simulation_id).eq("call_sid", call_sid).execute()
        
        if not existing_call.data:
            await create_call_record(simulation_id, call_sid)
        
        supabase.table("call_records").update({
            "transcript": transcript,
            "updated_at": datetime.now(UTC).isoformat()
        }).eq("simulation_id", simulation_id).eq("call_sid", call_sid).execute()
    except Exception as e:
        logger.error(f"Error updating call transcript: {str(e)}")
        raise 