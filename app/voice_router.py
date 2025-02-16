from fastapi import APIRouter, Request, WebSocket, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client
import json
import base64
import asyncio
import websockets
import logging
from typing import Optional, List, Dict
from uuid import uuid4
from app.database import create_call_record, update_call_record, supabase_client
from app.config import OPENAI_API_KEY, SYSTEM_MESSAGE, ssl_context, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, SUPABASE_URL, SUPABASE_KEY
from app.services.analysis_service import analyze_conversation
import os
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
job_counter = 0

@router.get("/", response_class=JSONResponse)
async def index():
    return {"message": "Voice Call Platform is running"}

@router.post("/test-call")
async def make_test_call(to_number: str):
    """Make a test call to a specified number."""
    try:
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Create call record first with a temporary call_sid
        call_record_id = await create_call_record(
            simulation_id="test_simulation",
            call_sid="pending",  # We'll update this with an incremental ID
            phone_number=to_number,
            user_id=str(uuid4()),  # Generate a random UUID for user_id
            status="initiated"  # Add initial status
        )
        
        # Make the call
        call = client.calls.create(
            to=to_number,
            from_=TWILIO_PHONE_NUMBER,
            url=f"https://9903-68-65-171-65.ngrok-free.app/incoming-call",
            record=True,
            status_callback=f"https://9903-68-65-171-65.ngrok-free.app/call-status",
            status_callback_event=['initiated', 'ringing', 'answered', 'completed']
        )
        
        # Update the call record with the actual call_sid
        await update_call_record(
            simulation_id="test_simulation",
            call_sid="pending",
            updates={
                "call_sid": call.sid
            }
        )
        
        return {
            "status": "success",
            "message": "Test call initiated",
            "call_sid": call.sid,
            "to_number": to_number
        }
    except Exception as e:
        logger.error(f"Error making test call: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.post("/call-status")
async def call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    Duration: Optional[int] = Form(None)
):
    """Handle call status updates."""
    logger.info(f"Call {CallSid} status update: {CallStatus}, Duration: {Duration}")
    try:
        # First, find the simulation_id for this call
        result = supabase_client.table('voice_conversations')\
            .select('simulation_id')\
            .eq('call_sid', CallSid)\
            .execute()
            
        if not result.data:
            logger.error(f"Could not find record for call {CallSid}")
            return HTMLResponse(content="", status_code=404)
            
        simulation_id = result.data[0]['simulation_id']
        
        updates = {
            "status": CallStatus
        }
        
        # Always update duration if provided, not just for completed calls
        if Duration is not None:
            updates["duration"] = Duration
            
        await update_call_record(
            simulation_id=simulation_id,  # Use the found simulation_id
            call_sid=CallSid,
            updates=updates
        )
        
        # Log when call is completed
        if CallStatus == "completed":
            logger.info(f"Call {CallSid} has completed. Duration: {Duration} seconds")
            
        return HTMLResponse(content="", status_code=200)
    except Exception as e:
        logger.error(f"Error updating call status: {str(e)}")
        return HTMLResponse(content="", status_code=500)

@router.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    logger.info(f"Received {request.method} request to /incoming-call")
    
    # Log request details for debugging
    if request.method == "POST":
        form_data = await request.form()
        logger.info(f"Form data: {dict(form_data)}")
    
    response = VoiceResponse()
    
    # Initial greeting
    response.say("Hello! I'm your AI assistant. How can I help you today?")
    
    # Create a Connect verb for media stream
    connect = Connect()
    connect.stream(url=f'wss://{request.url.hostname}/media-stream')
    response.append(connect)
    
    # Create a database record for POST requests
    if request.method == "POST":
        try:
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            to_number = form_data.get('To', 'unknown')
            if call_sid:
                # Find the existing record for this call
                result = supabase_client.table('voice_conversations')\
                    .select('simulation_id')\
                    .eq('call_sid', call_sid)\
                    .execute()
                
                if not result.data:
                    # If no record exists, create one with a default simulation_id
                    await create_call_record(
                        simulation_id="test_simulation",
                        call_sid=call_sid,
                        phone_number=to_number,
                        user_id=str(uuid4()),  # Generate a random UUID for user_id
                        status="initiated"
                    )
                    logger.info(f"Created database record for call {call_sid} to {to_number}")
        except Exception as e:
            logger.error(f"Error processing form data: {str(e)}")
    
    # Log the TwiML response for debugging
    logger.info(f"Returning TwiML: {str(response)}")
    return HTMLResponse(content=str(response), media_type="application/xml")

@router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected to media stream")
    
    # Connection state
    stream_sid = None
    current_call_sid = None
    current_simulation_id = None
    latest_media_timestamp = 0
    conversation_history = []
    message_timestamps = []  # Track message timestamps
    websocket_connected = True
    
    # Get the current system message
    current_system_message = os.getenv("SYSTEM_MESSAGE", 
        "You are a customer calling Bella Roma Italian restaurant. You are interested in ordering "
        "Italian food for dinner. You should ask about the menu, specials, and popular dishes. "
        "You're particularly interested in authentic Italian cuisine and might ask about appetizers, "
        "main courses, and desserts. Be friendly but also somewhat indecisive, as you want to hear "
        "about different options before making your choice. You can ask about ingredients, preparation "
        "methods, and portion sizes. If you like what you hear, you'll eventually place an order."
        "End every conversation with 'Goodbye!' or 'Bye' AND NOTHING ELSE"
    )
    logger.info(f"Using system message: {current_system_message}")
    
    try:
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            },
            ssl=ssl_context
        ) as openai_ws:
            # Initialize OpenAI session
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": "sage",
                    "instructions": current_system_message,
                    "modalities": ["text", "audio"],
                    "temperature": 0.7,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    }
                }
            }))

            # Send initial conversation prompt to make AI speak first
            initial_conversation = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Greet the user with 'Hello! What is on the menu for today?'"
                        }
                    ]
                }
            }
            await openai_ws.send(json.dumps(initial_conversation))
            await openai_ws.send(json.dumps({"type": "response.create"}))
            
            async def handle_twilio_messages():
                nonlocal stream_sid, current_call_sid, current_simulation_id, latest_media_timestamp, websocket_connected
                try:
                    while websocket_connected:
                        try:
                            message = await websocket.receive_text()
                            data = json.loads(message)
                            if data['event'] == 'media' and openai_ws.open:
                                latest_media_timestamp = int(data['media']['timestamp'])
                                await openai_ws.send(json.dumps({
                                    "type": "input_audio_buffer.append",
                                    "audio": data['media']['payload']
                                }))
                            elif data['event'] == 'start':
                                stream_sid = data['start']['streamSid']
                                current_call_sid = data['start'].get('callSid')
                                logger.info(f"Stream started: {stream_sid}, Call SID: {current_call_sid}")
                                
                                # Fetch existing record and transcript if any
                                if current_call_sid:
                                    try:
                                        # Find by call_sid
                                        result = supabase_client.table('voice_conversations')\
                                            .select('simulation_id, transcript')\
                                            .eq('call_sid', current_call_sid)\
                                            .execute()
                                        
                                        if result.data:
                                            current_simulation_id = result.data[0]['simulation_id']
                                            if result.data[0].get('transcript'):
                                                conversation_history = result.data[0]['transcript']
                                            logger.info(f"Found existing record with simulation_id: {current_simulation_id}")
                                    except Exception as e:
                                        logger.error(f"Error fetching existing transcript: {str(e)}")
                        except WebSocketDisconnect:
                            logger.info("WebSocket disconnected in Twilio message handler")
                            websocket_connected = False
                            break
                        except Exception as e:
                            logger.error(f"Error in Twilio message handler: {str(e)}")
                            websocket_connected = False
                            break
                except Exception as e:
                    logger.error(f"Error in Twilio message handler: {str(e)}")
                    websocket_connected = False
            
            async def handle_openai_messages():
                nonlocal websocket_connected
                try:
                    while websocket_connected and openai_ws.open:
                        try:
                            message = await openai_ws.recv()
                            response = json.loads(message)
                            
                            # Handle transcription
                            if response.get('type') == 'conversation.item.input_audio_transcription.completed':
                                transcript = response.get('transcript', '')
                                logger.info(f"User said: {transcript}")
                                if transcript.strip():  # Only add non-empty transcripts
                                    current_time = datetime.now().isoformat()
                                    conversation_history.append(f"User: {transcript}")
                                    message_timestamps.append({
                                        "message": f"User: {transcript}",
                                        "timestamp": current_time,
                                        "type": "user"
                                    })
                                    
                                    # Check for goodbye keywords in user's message
                                    if any(word.lower() in transcript.lower() for word in ["goodbye", "bye"]):
                                        logger.info("Goodbye detected in user message, ending call...")
                                        websocket_connected = False
                                        # Initialize Twilio client
                                        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                                        if current_call_sid:
                                            try:
                                                # End the call
                                                client.calls(current_call_sid).update(status="completed")
                                                logger.info(f"Call {current_call_sid} ended successfully")
                                                # Handle call completion
                                                await handle_call_completion(
                                                    current_call_sid,
                                                    current_simulation_id,
                                                    conversation_history,
                                                    message_timestamps
                                                )
                                            except Exception as e:
                                                logger.error(f"Error ending call: {str(e)}")
                                        break
                                    
                                    if current_call_sid and current_simulation_id:
                                        await update_call_record(
                                            simulation_id=current_simulation_id,
                                            call_sid=current_call_sid,
                                            updates={
                                                "transcript": conversation_history,
                                                "message_timestamps": message_timestamps
                                            }
                                        )
                            
                            # Handle audio responses
                            elif response.get('type') == 'response.audio.delta' and 'delta' in response:
                                audio_payload = base64.b64encode(
                                    base64.b64decode(response['delta'])).decode('utf-8')
                                if websocket_connected:
                                    await websocket.send_json({
                                        "event": "media",
                                        "streamSid": stream_sid,
                                        "media": {
                                            "payload": audio_payload
                                        }
                                    })
                            
                            # Handle completed assistant responses
                            elif response.get('type') == 'response.done':
                                response_data = response.get('response', {})
                                output = response_data.get('output', [])
                                for item in output:
                                    if item.get('role') == 'assistant' and item.get('content'):
                                        for content in item['content']:
                                            if content.get('type') == 'audio' and content.get('transcript'):
                                                assistant_text = content['transcript']
                                                current_time = datetime.now().isoformat()
                                                logger.info(f"Assistant response: {assistant_text}")
                                                conversation_history.append(f"Assistant: {assistant_text}")
                                                message_timestamps.append({
                                                    "message": f"Assistant: {assistant_text}",
                                                    "timestamp": current_time,
                                                    "type": "assistant"
                                                })
                                                
                                                # Check for goodbye keywords in assistant's message
                                                if any(word.lower() in assistant_text.lower() for word in ["goodbye", "bye"]):
                                                    logger.info("Goodbye detected in assistant message, ending call...")
                                                    websocket_connected = False
                                                    # Initialize Twilio client
                                                    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                                                    if current_call_sid:
                                                        try:
                                                            # End the call
                                                            client.calls(current_call_sid).update(status="completed")
                                                            logger.info(f"Call {current_call_sid} ended successfully")
                                                            # Handle call completion
                                                            await handle_call_completion(
                                                                current_call_sid,
                                                                current_simulation_id,
                                                                conversation_history,
                                                                message_timestamps
                                                            )
                                                        except Exception as e:
                                                            logger.error(f"Error ending call: {str(e)}")
                                                    break
                                                
                                                if current_call_sid and current_simulation_id:
                                                    await update_call_record(
                                                        simulation_id=current_simulation_id,
                                                        call_sid=current_call_sid,
                                                        updates={
                                                            "transcript": conversation_history,
                                                            "message_timestamps": message_timestamps
                                                        }
                                                    )
                        except WebSocketDisconnect:
                            logger.info("WebSocket disconnected in OpenAI message handler")
                            websocket_connected = False
                            break
                        except Exception as e:
                            logger.error(f"Error in OpenAI message handler: {str(e)}")
                            websocket_connected = False
                            break
                except Exception as e:
                    logger.error(f"Error in OpenAI message handler: {str(e)}")
                    websocket_connected = False
            
            await asyncio.gather(handle_twilio_messages(), handle_openai_messages())
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {str(e)}")
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
        logger.info("WebSocket connection closed")

@router.get("/transcript", response_class=JSONResponse)
async def get_transcript(
    simulation_id: Optional[str] = None, 
    call_sid: Optional[str] = None
):
    """Get transcript for a specific call or latest transcript."""
    try:
        query = supabase_client.table('voice_conversations').select('*')
        
        if simulation_id:
            query = query.eq('simulation_id', simulation_id)
        if call_sid:
            query = query.eq('call_sid', call_sid)
            
        result = query.order('created_at', desc=True).limit(1).execute()
        
        if result.data:
            return {
                "simulation_id": result.data[0]["simulation_id"],
                "call_sid": result.data[0]["call_sid"],
                "status": result.data[0]["status"],
                "transcript": result.data[0]["transcript"] if result.data[0].get("transcript") else []
            }
        return {"transcript": []}
    except Exception as e:
        logger.error(f"Error getting transcript: {str(e)}")
        return {"transcript": []}

@router.get("/test-db")
async def test_db():
    try:
        # Try to query the table
        result = supabase_client.table('voice_conversations').select('*').limit(1).execute()
        return {"status": "success", "data": result.data}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "url": SUPABASE_URL,
            "key_prefix": SUPABASE_KEY[:6] if SUPABASE_KEY else None
        }

@router.post("/batch-test-calls")
async def make_batch_test_calls(to_number: str, num_calls: int = 1):
    """Make multiple test calls to a specified number."""
    if num_calls > 10:
        return {
            "status": "error",
            "message": "Maximum number of concurrent calls is 10"
        }
    
    try:
        calls = []
        # Create multiple calls
        for i in range(num_calls):
            try:
                # Initialize Twilio client
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                
                # Create call record first
                call_record_id = await create_call_record(
                    simulation_id=f"test_simulation_{i}",
                    call_sid="pending",
                    phone_number=to_number,
                    user_id=str(uuid4()),  # Generate a random UUID for user_id
                    status="initiated"  # Add initial status
                )
                
                # Add a small delay between calls to prevent overwhelming the system
                if i > 0:
                    await asyncio.sleep(10)
                
                # Make the call
                call = client.calls.create(
                    to=to_number,
                    from_=TWILIO_PHONE_NUMBER,
                    url=f"https://9903-68-65-171-65.ngrok-free.app/incoming-call",
                    record=True,
                    status_callback=f"https://9903-68-65-171-65.ngrok-free.app/call-status",
                    status_callback_event=['initiated', 'ringing', 'answered', 'completed']
                )
                
                # Update the call record with the actual call_sid
                await update_call_record(
                    simulation_id=f"test_simulation_{i}",
                    call_sid="pending",
                    updates={
                        "call_sid": call.sid
                    }
                )
                
                calls.append({
                    "call_number": i + 1,
                    "call_sid": call.sid,
                    "to_number": to_number,
                    "status": "initiated"
                })
                
                logger.info(f"Initiated call {i + 1} with SID: {call.sid}")
                
            except Exception as e:
                logger.error(f"Error making call {i + 1}: {str(e)}")
                calls.append({
                    "call_number": i + 1,
                    "error": str(e)
                })
        
        return {
            "status": "success",
            "message": f"Initiated {num_calls} test calls",
            "calls": calls
        }
        
    except Exception as e:
        logger.error(f"Error in batch call creation: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.get("/batch-status")
async def get_batch_status():
    """Get the status of all active test calls."""
    try:
        result = supabase_client.table('voice_conversations')\
            .select('*')\
            .order('created_at', desc=True)\
            .limit(10)\
            .execute()
        
        calls = []
        for record in result.data:
            calls.append({
                "simulation_id": record["simulation_id"],
                "call_sid": record["call_sid"],
                "status": record["status"],
                "phone_number": record["phone_number"],
                "transcript": record.get("transcript", [])
            })
        
        return {
            "status": "success",
            "calls": calls
        }
    except Exception as e:
        logger.error(f"Error getting batch status: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@router.post("/multi-call")
async def make_multiple_calls(to_number: str, num_calls: int = 1):
    """Make multiple calls by invoking /test-call endpoint multiple times."""
    if num_calls > 10:
        return {
            "status": "error",
            "message": "Maximum number of concurrent calls is 10"
        }
    
    try:
        global job_counter
        job_counter += 1
        current_job_id = f"job_{job_counter}"
        
        calls = []
        for i in range(num_calls):
            try:
                # Initialize Twilio client
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                
                # Create call record first with the job ID
                call_record = await create_call_record(
                    simulation_id=current_job_id,
                    call_sid=f"pending_{i}",  # Temporary call_sid
                    phone_number=to_number,
                    user_id=str(uuid4()),  # Generate random UUID for user_id
                    status="initiated"
                )
                
                # Add a delay between calls
                if i > 0:
                    await asyncio.sleep(10)
                
                # Make the call
                call = client.calls.create(
                    to=to_number,
                    from_=TWILIO_PHONE_NUMBER,
                    url=f"https://9903-68-65-171-65.ngrok-free.app/incoming-call",
                    record=True,
                    status_callback=f"https://9903-68-65-171-65.ngrok-free.app/call-status",
                    status_callback_event=['initiated', 'ringing', 'answered', 'completed']
                )
                
                # Update the call record with the actual call_sid
                await update_call_record(
                    simulation_id=current_job_id,
                    call_sid=f"pending_{i}",
                    updates={
                        "call_sid": call.sid,
                        "transcript": []  # Initialize empty transcript array
                    }
                )
                
                calls.append({
                    "job_id": current_job_id,
                    "call_number": i + 1,
                    "call_sid": call.sid,
                    "to_number": to_number,
                    "status": "initiated"
                })
                
                logger.info(f"Initiated call {i + 1} with job ID: {current_job_id}, call_sid: {call.sid}")
                
            except Exception as e:
                logger.error(f"Error making call {i + 1}: {str(e)}")
                calls.append({
                    "job_id": current_job_id,
                    "call_number": i + 1,
                    "status": "error",
                    "message": str(e)
                })
        
        return {
            "status": "success",
            "message": f"Initiated {num_calls} test calls",
            "job_id": current_job_id,
            "calls": calls
        }
        
    except Exception as e:
        logger.error(f"Error in multiple call creation: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

async def handle_call_completion(current_call_sid: str, current_simulation_id: str, conversation_history: List[str], message_timestamps: List[Dict]):
    """Handle call completion and trigger analysis."""
    try:
        logger.info(f"Starting call completion handling for call {current_call_sid}")
        
        # Update call record
        await update_call_record(
            simulation_id=current_simulation_id,
            call_sid=current_call_sid,
            updates={
                "status": "completed",
                "transcript": conversation_history,
                "message_timestamps": message_timestamps
            }
        )
        logger.info(f"Updated call record with final transcript for call {current_call_sid}")
        
        # Get the conversation ID from the database
        result = supabase_client.table('voice_conversations')\
            .select('id')\
            .eq('call_sid', current_call_sid)\
            .execute()
            
        if result.data:
            conversation_id = result.data[0]['id']
            logger.info(f"Starting conversation analysis for call {current_call_sid} (conversation_id: {conversation_id})")
            # Trigger analysis
            await analyze_conversation(conversation_id, message_timestamps)
            logger.info(f"Completed conversation analysis for call {current_call_sid}")
        else:
            logger.error(f"Could not find conversation ID for call {current_call_sid}")
            
    except Exception as e:
        logger.error(f"Error in call completion handling: {str(e)}")

@router.post("/execute_large_calls")
async def execute_large_calls(to_number: str, total_calls: int = 2):
    """Execute multiple calls in batches of 2, waiting for each batch to complete before starting the next."""
    if total_calls > 10:
        return {
            "status": "error",
            "message": "Maximum number of total calls is 10"
        }
    
    try:
        all_calls = []
        batch_size = 2
        num_batches = (total_calls + batch_size - 1) // batch_size  # Ceiling division
        
        for batch in range(num_batches):
            remaining_calls = total_calls - (batch * batch_size)
            current_batch_size = min(batch_size, remaining_calls)
            
            logger.info(f"Starting batch {batch + 1} with {current_batch_size} calls")
            
            # Make the batch of calls
            batch_response = await make_multiple_calls(to_number, current_batch_size)
            
            if batch_response["status"] == "error":
                return {
                    "status": "error",
                    "message": f"Error in batch {batch + 1}: {batch_response['message']}",
                    "completed_calls": all_calls
                }
            
            # Track the calls from this batch
            current_batch_calls = batch_response["calls"]
            all_calls.extend(current_batch_calls)
            
            # Wait for all calls in this batch to complete
            for call in current_batch_calls:
                call_sid = call["call_sid"]
                job_id = call["job_id"]
                
                # Poll until the call is completed
                while True:
                    result = supabase_client.table('voice_conversations')\
                        .select('status, transcript')\
                        .eq('call_sid', call_sid)\
                        .execute()
                    
                    if not result.data:
                        logger.error(f"Could not find record for call {call_sid}")
                        break
                        
                    status = result.data[0]['status']
                    if status == "completed":
                        # Ensure we have a transcript and the analysis is done
                        transcript = result.data[0].get('transcript', [])
                        if transcript:
                            logger.info(f"Call {call_sid} completed with transcript")
                            break
                    elif status in ["failed", "busy", "no-answer", "canceled"]:
                        logger.warning(f"Call {call_sid} ended with status: {status}")
                        break
                        
                    # Wait before checking again
                    await asyncio.sleep(5)
            
            # Add a delay between batches
            if batch < num_batches - 1:
                logger.info(f"Batch {batch + 1} completed, waiting before starting next batch")
                await asyncio.sleep(15)
        
        return {
            "status": "success",
            "message": f"Completed {total_calls} calls in {num_batches} batches",
            "calls": all_calls
        }
        
    except Exception as e:
        logger.error(f"Error in large calls execution: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "completed_calls": all_calls
        } 