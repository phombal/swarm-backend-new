from typing import Dict, List
from datetime import datetime
import asyncio
import logging
import websockets
import json
import base64

# Import local modules
from app.services.twilio_service import TwilioService
from app.database import get_db
from app.config import (
    OPENAI_API_KEY,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    STRATIFY_BASE_URL
)

logger = logging.getLogger(__name__)

class TestRunner:
    def __init__(
        self,
        simulation_id: str,
        target_phone: str,
        concurrent_calls: int,
        scenario: Dict
    ):
        self.simulation_id = simulation_id
        self.target_phone = target_phone
        self.concurrent_calls = concurrent_calls
        self.scenario = scenario
        self.twilio_service = TwilioService()
        self.active_calls: Dict[str, asyncio.Task] = {}
        self.should_stop = False

    async def run_simulation(self):
        """
        Run the test simulation with the specified number of concurrent calls.
        """
        try:
            logger.info(f"Starting simulation {self.simulation_id} with {self.concurrent_calls} concurrent calls")
            
            # Update simulation status to running
            db = await get_db()
            await db.update_simulation_status(self.simulation_id, "running")
            
            # Create tasks for concurrent calls
            tasks = []
            for i in range(self.concurrent_calls):
                task = asyncio.create_task(self.handle_single_call(i))
                tasks.append(task)
            
            # Wait for all calls to complete
            await asyncio.gather(*tasks)
            
            # Update simulation status to completed
            await db.update_simulation_status(self.simulation_id, "completed")
            
            logger.info(f"Simulation {self.simulation_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error in simulation {self.simulation_id}: {str(e)}")
            # Update simulation status to failed
            await db.update_simulation_status(self.simulation_id, "failed", error=str(e))

    async def handle_single_call(self, call_index: int):
        """
        Handle a single call simulation.
        """
        try:
            # Initiate call through Twilio
            call = await self.twilio_service.create_call(
                to=self.target_phone,
                from_=TWILIO_PHONE_NUMBER,
                url=f"{STRATIFY_BASE_URL}/incoming-call"
            )
            
            call_sid = call.sid
            self.active_calls[call_sid] = asyncio.current_task()
            
            # Connect to OpenAI Realtime API
            async with websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
                extra_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                }
            ) as openai_ws:
                # Initialize session with scenario context
                await self.initialize_session(openai_ws)
                
                # Process the conversation based on scenario
                await self.process_conversation(openai_ws, call_sid)
                
        except Exception as e:
            logger.error(f"Error in call {call_index}: {str(e)}")
            raise
        finally:
            if call_sid in self.active_calls:
                del self.active_calls[call_sid]

    async def initialize_session(self, websocket):
        """
        Initialize the OpenAI session with scenario context.
        """
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": self.scenario.get("voice", "sage"),
                "instructions": self.scenario.get("system_message", ""),
                "modalities": ["text", "audio"],
                "temperature": 0.7,
                "input_audio_transcription": {
                    "model": "whisper-1"
                }
            }
        }
        await websocket.send(json.dumps(session_update))

    async def process_conversation(self, websocket, call_sid: str):
        """
        Process the conversation based on the scenario.
        """
        db = await get_db()
        conversation_transcript = []
        
        try:
            while not self.should_stop:
                # Receive message from OpenAI
                message = await websocket.recv()
                response = json.loads(message)
                
                # Handle different types of responses
                if response.get("type") == "conversation.item.input_audio_transcription.completed":
                    transcript = response.get("transcript", "")
                    conversation_transcript.append(f"User: {transcript}")
                    
                elif response.get("type") == "response.text.delta" and "text" in response:
                    assistant_text = response["text"]
                    conversation_transcript.append(f"Assistant: {assistant_text}")
                
                # Update database with conversation progress
                await db.update_call_transcript(
                    simulation_id=self.simulation_id,
                    call_sid=call_sid,
                    transcript=conversation_transcript
                )
                
                # Check if conversation should end based on scenario
                if await self.should_end_conversation(conversation_transcript):
                    break
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket connection closed for call {call_sid}")
        except Exception as e:
            logger.error(f"Error processing conversation for call {call_sid}: {str(e)}")
            raise

    async def should_end_conversation(self, transcript: List[str]) -> bool:
        """
        Check if the conversation should end based on scenario conditions.
        """
        # Implement scenario-specific ending conditions
        max_turns = self.scenario.get("max_turns", 10)
        return len(transcript) >= max_turns * 2  # *2 because each turn has user and assistant message

    async def stop_simulation(self):
        """
        Stop the ongoing simulation.
        """
        self.should_stop = True
        # Cancel all active calls
        for task in self.active_calls.values():
            task.cancel() 