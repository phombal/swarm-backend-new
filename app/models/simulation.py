from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class SimulationCreate(BaseModel):
    target_phone: str
    concurrent_calls: int = Field(gt=0, le=100)  # Limit max concurrent calls
    scenario: Dict = Field(...)
    
    class Config:
        json_schema_extra = {
            "example": {
                "target_phone": "+1234567890",
                "concurrent_calls": 5,
                "scenario": {
                    "voice": "sage",
                    "system_message": "You are a customer calling to place an order.",
                    "max_turns": 10,
                    "conversation_flow": [
                        {"role": "user", "content": "I'd like to place an order for delivery."},
                        {"role": "assistant", "content": "I'll help you with that. What would you like to order?"}
                    ]
                }
            }
        }

class SimulationResponse(BaseModel):
    id: str
    status: str
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SimulationStatus(BaseModel):
    id: str
    status: str
    active_calls: int
    completed_calls: int
    failed_calls: int
    start_time: datetime
    end_time: Optional[datetime] = None
    error: Optional[str] = None

class CallRecord(BaseModel):
    simulation_id: str
    call_sid: str
    status: str
    duration: Optional[int] = None
    transcript: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class SimulationResults(BaseModel):
    simulation_id: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    average_duration: float
    transcripts: Dict[str, List[str]]  # call_sid -> transcript
    metrics: Dict[str, float]  # Custom metrics like response time, success rate, etc. 