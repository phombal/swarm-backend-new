from fastapi import APIRouter, Request, WebSocket, Form
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Connect, Start
from app.websocket_handler import handle_media_stream
from app.database import create_call_record, update_call_record, update_call_transcript, supabase_client
from typing import Optional
import asyncio
import logging
from app.config import SUPABASE_URL, SUPABASE_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

transcript = []

@router.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@router.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    logger.info(f"Received {request.method} request to /incoming-call")
    response = VoiceResponse()
    
    # First say the greeting
    response.say("Please wait while we connect your call to Bella Roma Italian Cuisine.")
    
    # Start recording in the background
    recording_task = asyncio.create_task(start_recording(response, request))

    # Create a Connect verb to maintain the stream
    connect = Connect()
    connect.stream(url=f'wss://{request.url.hostname}/media-stream')
    response.append(connect)

    # Wait for the recording task to complete if needed
    await recording_task
    
    # Create a record in the database only for POST requests
    if request.method == "POST":
        try:
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            logger.info(f"Processing call with SID: {call_sid}")
            if call_sid:
                await create_call_record("test_simulation", call_sid)  # Using a test simulation ID for now
                logger.info(f"Created database record for call {call_sid}")
        except Exception as e:
            logger.error(f"Error processing form data: {str(e)}")
    
    logger.info("Returning TwiML response")
    return HTMLResponse(content=str(response), media_type="application/xml")

async def start_recording(response: VoiceResponse, request: Request):
    # Start recording in the background
    response.record(
        action=f'https://{request.url.hostname}/recording-complete',
        recordingStatusCallback=f'https://{request.url.hostname}/recording-complete',
        recordingStatusCallbackMethod='POST',
        transcribe=True,
        transcribeCallback=f'https://{request.url.hostname}/transcription-complete',
        playBeep=False,
        trim='trim-silence'  # Add trim silence option
    )
    logger.info("Recording started in the background")

@router.post("/handle-input")
async def handle_input(request: Request):
    logger.info("Received input from caller")
    response = VoiceResponse()
    
    # Create a Connect verb to maintain the stream
    connect = Connect()
    connect.stream(url=f'wss://{request.url.hostname}/media-stream')
    response.append(connect)
    
    return HTMLResponse(content=str(response), media_type="application/xml")

@router.post("/recording-complete")
async def recording_complete(
    RecordingUrl: str = Form(...),
    CallSid: str = Form(...),
    RecordingDuration: Optional[int] = Form(None),
    RecordingStatus: Optional[str] = Form(None)
):
    logger.info(f"Recording complete for call {CallSid}. Status: {RecordingStatus}, URL: {RecordingUrl}")
    try:
        await update_call_record(
            simulation_id="test_simulation",  # Using a test simulation ID for now
            call_sid=CallSid,
            updates={
                "recording_url": RecordingUrl,
                "duration": RecordingDuration,
                "status": "recorded"
            }
        )
        logger.info(f"Updated database with recording URL: {RecordingUrl}")
    except Exception as e:
        logger.error(f"Error updating recording information: {str(e)}")
    return HTMLResponse(content="", media_type="application/xml")

@router.post("/transcription-complete")
async def transcription_complete(
    TranscriptionText: str = Form(...),
    CallSid: str = Form(...),
    TranscriptionStatus: Optional[str] = Form(None)
):
    logger.info(f"Transcription complete for call {CallSid}. Status: {TranscriptionStatus}")
    try:
        await update_call_record(
            simulation_id="test_simulation",  # Using a test simulation ID for now
            call_sid=CallSid,
            updates={
                "transcription": TranscriptionText,
                "status": "completed"
            }
        )
        logger.info(f"Updated database with transcription for call {CallSid}")
    except Exception as e:
        logger.error(f"Error updating transcription: {str(e)}")
    return HTMLResponse(content="", media_type="application/xml")

@router.get("/transcript", response_class=JSONResponse)
async def get_transcript():
    try:
        result = supabase_client.table('call_records').select('transcription').order('created_at', desc=True).limit(1).execute()
        return {"transcript": result.data[0]["transcription"] if result.data else ""}
    except Exception as e:
        logger.error(f"Error getting latest transcript: {str(e)}")
        return {"transcript": ""}

@router.websocket("/media-stream")
async def websocket_endpoint(websocket: WebSocket):
    await handle_media_stream(websocket, transcript)

@router.get("/test-db")
async def test_db():
    try:
        # Try to query the table
        result = supabase_client.table('call_records').select('*').limit(1).execute()
        return {"status": "success", "data": result.data}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "url": SUPABASE_URL,
            "key_prefix": SUPABASE_KEY[:6] if SUPABASE_KEY else None
        } 