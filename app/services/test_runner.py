from typing import Dict, List
from datetime import datetime
import asyncio
import logging
import websockets
import json
import base64

# Import local modules
from app.services.twilio_service import TwilioService
from app.database import (
    update_simulation_status,
    create_call_record,
    update_call_record,
    update_call_transcript
)
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
            await update_simulation_status(self.simulation_id, "running")
            
            # Create tasks for concurrent calls
            tasks = []
            for i in range(self.concurrent_calls):
                task = asyncio.create_task(self.handle_single_call(i))
                tasks.append(task)
            
            # Wait for all calls to complete
            await asyncio.gather(*tasks)
            
            # Update simulation status to completed
            await update_simulation_status(self.simulation_id, "completed")
            
            logger.info(f"Simulation {self.simulation_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error in simulation {self.simulation_id}: {str(e)}")
            # Update simulation status to failed
            await update_simulation_status(self.simulation_id, "failed", error=str(e))
            raise

    async def handle_single_call(self, call_index: int):
        """
        Handle a single call simulation with real-time conversation.
        """
        call_sid = None
        try:
            logger.info(f"Call {call_index}: Target phone: {self.target_phone}")
            logger.info(f"Call {call_index}: From phone: {TWILIO_PHONE_NUMBER}")
            
            # Connect to OpenAI Realtime API
            logger.info(f"Call {call_index}: Connecting to OpenAI Realtime API...")
            async with websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
                extra_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                }
            ) as openai_ws:
                # Initialize OpenAI session
                logger.info(f"Call {call_index}: Initializing OpenAI session...")
                await self.initialize_session(openai_ws)
                
                # Initiate call through Twilio with streaming
                logger.info(f"Call {call_index}: Initiating Twilio call with streaming...")
                call = await self.twilio_service.create_call(
                    to=self.target_phone,
                    from_=TWILIO_PHONE_NUMBER
                )
                
                call_sid = call.sid
                logger.info(f"Call {call_index}: Call created with SID: {call_sid}")
                self.active_calls[call_sid] = asyncio.current_task()
                
                # Create call record
                logger.info(f"Call {call_index}: Creating call record in database...")
                await create_call_record(self.simulation_id, call_sid)
                
                # Process the conversation
                logger.info(f"Call {call_index}: Starting conversation processing...")
                conversation_transcript = []
                
                while True:
                    # Receive message from OpenAI
                    message = await openai_ws.recv()
                    response = json.loads(message)
                    
                    # Handle different types of responses
                    if response.get("type") == "conversation.item.input_audio_transcription.completed":
                        transcript = response.get("transcript", "")
                        logger.info(f"Call {call_index}: User said: {transcript}")
                        conversation_transcript.append(f"User: {transcript}")
                        
                    elif response.get("type") == "response.text.delta" and "text" in response:
                        assistant_text = response["text"]
                        logger.info(f"Call {call_index}: Assistant said: {assistant_text}")
                        conversation_transcript.append(f"Assistant: {assistant_text}")
                    
                    # Update database with conversation progress
                    await update_call_transcript(
                        simulation_id=self.simulation_id,
                        call_sid=call_sid,
                        transcript=conversation_transcript
                    )
                    
                    # Check call status
                    status = await self.twilio_service.get_call_status(call_sid)
                    if status in ["completed", "failed", "no-answer"]:
                        logger.info(f"Call {call_index}: Call ended with status: {status}")
                        await update_call_record(self.simulation_id, call_sid, {"status": status})
                        break
                    
                    # Check if we should end based on scenario
                    if await self.should_end_conversation(conversation_transcript):
                        logger.info(f"Call {call_index}: Conversation completed based on scenario")
                        await update_call_record(self.simulation_id, call_sid, {"status": "completed"})
                        break
                    
                    await asyncio.sleep(0.1)  # Small delay to prevent tight loop
                
        except Exception as e:
            logger.error(f"Error in call {call_index}: {str(e)}")
            if call_sid:
                await update_call_record(self.simulation_id, call_sid, {"status": "failed"})
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
                await update_call_transcript(
                    simulation_id=self.simulation_id,
                    call_sid=call_sid,
                    transcript=conversation_transcript
                )
                
                # Check if conversation should end based on scenario
                if await self.should_end_conversation(conversation_transcript):
                    await update_call_record(self.simulation_id, call_sid, {"status": "completed"})
                    break
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket connection closed for call {call_sid}")
            await update_call_record(self.simulation_id, call_sid, {"status": "completed"})
        except Exception as e:
            logger.error(f"Error processing conversation for call {call_sid}: {str(e)}")
            await update_call_record(self.simulation_id, call_sid, {"status": "failed"})
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