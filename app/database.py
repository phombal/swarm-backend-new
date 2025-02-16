from typing import Dict
import logging
from datetime import datetime, UTC
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

try:
    supabase_client: Client = create_client(
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
        supabase_client.table("voice_conversations").select("count", count="exact").execute()
        logger.info("Database connection initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database connection: {str(e)}")
        raise

async def create_call_record(simulation_id: str, call_sid: str, phone_number: str, status: str = "initiated") -> str:
    """Create a new voice conversation record."""
    try:
        result = supabase_client.table("voice_conversations").insert({
            "simulation_id": simulation_id,
            "call_sid": call_sid,
            "phone_number": phone_number,
            "status": status,
            "transcript": [],  # Initialize with empty array
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat()
        }).execute()
        
        return result.data[0]["id"]
    except Exception as e:
        logger.error(f"Error creating voice conversation record: {str(e)}")
        raise

async def update_call_record(
    simulation_id: str,
    call_sid: str,
    updates: Dict
) -> bool:
    """Update a voice conversation record."""
    try:
        # Ensure updated_at is set
        updates["updated_at"] = datetime.now(UTC).isoformat()
        
        # If updating transcript, ensure it's a list
        if "transcript" in updates and updates["transcript"] is None:
            updates["transcript"] = []
        
        # First try to find by call_sid
        response = supabase_client.table('voice_conversations')\
            .update(updates)\
            .eq('simulation_id', simulation_id)\
            .eq('call_sid', call_sid)\
            .execute()
            
        if not response.data:
            # If no record found by call_sid, try twilio_call_sid
            response = supabase_client.table('voice_conversations')\
                .update(updates)\
                .eq('simulation_id', simulation_id)\
                .eq('twilio_call_sid', call_sid)\
                .execute()
        
        return bool(response.data)
    except Exception as e:
        logger.error(f"Error updating voice conversation record: {str(e)}")
        return False 