from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, UUID4

class VoiceConversation(BaseModel):
    id: UUID4
    simulation_id: str
    call_sid: str
    phone_number: str
    status: str
    duration: Optional[int] = None
    transcript: List[Dict] = []
    message_timestamps: List[Dict] = []
    token_counts: Dict = {}
    response_times: List[Dict] = []
    error_details: List[Dict] = []
    conversation_metrics: Dict = {}
    user_id: UUID4
    created_at: datetime
    updated_at: datetime
    error_severity: Optional[str] = None
    recovery_attempt: Optional[str] = None
    recovery_success: Optional[bool] = None 