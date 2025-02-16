from typing import Dict, Optional
import logging
from datetime import datetime, UTC
from uuid import uuid4
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

async def create_call_record(simulation_id: str, call_sid: str, phone_number: str, user_id: str, status: str = "initiated") -> str:
    """Create a new voice conversation record."""
    try:
        now = datetime.now(UTC).isoformat()
        result = supabase_client.table("voice_conversations").insert({
            "id": str(uuid4()),
            "simulation_id": simulation_id,
            "call_sid": call_sid,
            "phone_number": phone_number,
            "status": status,
            "duration": None,
            "transcript": [],
            "message_timestamps": [],
            "token_counts": {},
            "response_times": [],
            "error_details": [],
            "conversation_metrics": {},
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "error_severity": None,
            "recovery_attempt": None,
            "recovery_success": None
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
        
        # Initialize empty lists/dicts for JSON fields if they're None
        json_fields = ["transcript", "message_timestamps", "token_counts", 
                      "response_times", "error_details", "conversation_metrics"]
        for field in json_fields:
            if field in updates and updates[field] is None:
                updates[field] = [] if field != "token_counts" and field != "conversation_metrics" else {}
        
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