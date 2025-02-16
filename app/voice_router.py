from fastapi import APIRouter, Request, WebSocket, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client
import json
import base64
import asyncio
import websockets
import logging
from typing import Optional, List
from app.database import create_call_record, update_call_record, supabase_client
from app.config import OPENAI_API_KEY, SYSTEM_MESSAGE, ssl_context, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, SUPABASE_URL, SUPABASE_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
conversation_history: List[str] = []

@router.get("/", response_class=JSONResponse)
async def index():
    return {"message": "Voice Call Platform is running"}

@router.post("/test-call")
async def make_test_call(to_number: str):
    """Make a test call to a specified number."""
    try:
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Create call record first
        call_record_id = await create_call_record(
            simulation_id="test_simulation",
            call_sid="pending",  # We'll update this after the call is created
            phone_number=to_number
        )
        
        # Make the call
        call = client.calls.create(
            to=to_number,
            from_=TWILIO_PHONE_NUMBER,
            url=f"https://64bf-171-64-77-68.ngrok-free.app/incoming-call",
            record=True,
            status_callback=f"https://64bf-171-64-77-68.ngrok-free.app/call-status",
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
        await update_call_record(
            simulation_id="test_simulation",
            call_sid=CallSid,
            updates={
                "status": CallStatus,
                "duration": Duration
            }
        )
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
                # Only create a new record if one doesn't exist
                result = supabase_client.table('voice_conversations')\
                    .select('id')\
                    .eq('call_sid', call_sid)\
                    .execute()
                
                if not result.data:
                    await create_call_record(
                        simulation_id="test_simulation",
                        call_sid=call_sid,
                        phone_number=to_number
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
    latest_media_timestamp = 0
    
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
                "instructions": SYSTEM_MESSAGE,
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
            nonlocal stream_sid, current_call_sid, latest_media_timestamp
            try:
                async for message in websocket.iter_text():
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
            except WebSocketDisconnect:
                logger.info("Client disconnected")
                if openai_ws.open:
                    await openai_ws.close()
        
        async def handle_openai_messages():
            try:
                async for message in openai_ws:
                    response = json.loads(message)
                    
                    # Handle transcription
                    if response.get('type') == 'conversation.item.input_audio_transcription.completed':
                        transcript = response.get('transcript', '')
                        logger.info(f"User said: {transcript}")
                        conversation_history.append(f"User: {transcript}")
                        if current_call_sid:
                            await update_call_record(
                                simulation_id="test_simulation",
                                call_sid=current_call_sid,
                                updates={"transcript": conversation_history}
                            )
                    
                    # Handle audio responses
                    elif response.get('type') == 'response.audio.delta' and 'delta' in response:
                        audio_payload = base64.b64encode(
                            base64.b64decode(response['delta'])).decode('utf-8')
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
                                        logger.info(f"Assistant response: {assistant_text}")
                                        conversation_history.append(f"Assistant: {assistant_text}")
                                        if current_call_sid:
                                            await update_call_record(
                                                simulation_id="test_simulation",
                                                call_sid=current_call_sid,
                                                updates={"transcript": conversation_history}
                                            )
            except Exception as e:
                logger.error(f"Error in OpenAI message handling: {str(e)}")
        
        await asyncio.gather(handle_twilio_messages(), handle_openai_messages())

@router.get("/transcript", response_class=JSONResponse)
async def get_transcript():
    try:
        result = supabase_client.table('voice_conversations').select('transcript').order('created_at', desc=True).limit(1).execute()
        return {"transcript": result.data[0]["transcript"] if result.data else []}
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