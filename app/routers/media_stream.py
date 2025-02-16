from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect
import json
import base64
import asyncio
import logging
import websockets
from app.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/media-stream")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("Client connected to media stream")
    await websocket.accept()
    
    # Connection specific state
    stream_sid = None
    latest_media_timestamp = 0
    last_assistant_item = None
    mark_queue = []
    response_start_timestamp_twilio = None
    conversation_transcript = []

    async def receive_from_twilio():
        nonlocal stream_sid, latest_media_timestamp
        try:
            async for message in websocket.iter_text():
                data = json.loads(message)
                if data['event'] == 'media' and openai_ws.open:
                    latest_media_timestamp = int(data['media']['timestamp'])
                    audio_append = {
                        "type": "input_audio_buffer.append",
                        "audio": data['media']['payload']
                    }
                    await openai_ws.send(json.dumps(audio_append))
                elif data['event'] == 'start':
                    stream_sid = data['start']['streamSid']
                    logger.info(f"Incoming stream started: {stream_sid}")
                    response_start_timestamp_twilio = None
                    latest_media_timestamp = 0
                    last_assistant_item = None
                elif data['event'] == 'mark':
                    if mark_queue:
                        mark_queue.pop(0)
                elif data['event'] == "stop":
                    if openai_ws.open:
                        await openai_ws.close()
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            if openai_ws.open:
                await openai_ws.close()

    async def send_to_twilio():
        nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
        try:
            async for openai_message in openai_ws:
                response = json.loads(openai_message)
                logger.debug(f"Received OpenAI event: {response['type']}")

                # Handle audio responses
                if response.get('type') == 'response.audio.delta' and 'delta' in response:
                    audio_payload = base64.b64encode(
                        base64.b64decode(response['delta'])).decode('utf-8')
                    audio_delta = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": audio_payload
                        }
                    }
                    await websocket.send_json(audio_delta)

                    if response_start_timestamp_twilio is None:
                        response_start_timestamp_twilio = latest_media_timestamp
                        logger.debug(f"Setting start timestamp: {response_start_timestamp_twilio}ms")

                    if response.get('item_id'):
                        last_assistant_item = response['item_id']

                    await send_mark(websocket, stream_sid)

                # Handle speech interruption
                if response.get('type') == 'input_audio_buffer.speech_started':
                    logger.info("Speech started detected")
                    if last_assistant_item:
                        logger.info(f"Interrupting response: {last_assistant_item}")
                        await handle_speech_started_event()

        except Exception as e:
            logger.error(f"Error in send_to_twilio: {e}")

    async def handle_speech_started_event():
        nonlocal response_start_timestamp_twilio, last_assistant_item
        if mark_queue and response_start_timestamp_twilio is not None:
            elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
            
            if last_assistant_item:
                truncate_event = {
                    "type": "conversation.item.truncate",
                    "item_id": last_assistant_item,
                    "content_index": 0,
                    "audio_end_ms": elapsed_time
                }
                await openai_ws.send(json.dumps(truncate_event))

            await websocket.send_json({
                "event": "clear",
                "streamSid": stream_sid
            })

            mark_queue.clear()
            last_assistant_item = None
            response_start_timestamp_twilio = None

    async def send_mark(connection, stream_sid):
        if stream_sid:
            mark_event = {
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {"name": "responsePart"}
            }
            await connection.send_json(mark_event)
            mark_queue.append('responsePart')

    # Connect to OpenAI
    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        # Initialize OpenAI session
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": "sage",
                "instructions": "You are a helpful AI assistant.",
                "modalities": ["text", "audio"],
                "temperature": 0.7,
                "input_audio_transcription": {
                    "model": "whisper-1"
                }
            }
        }
        await openai_ws.send(json.dumps(session_update))
        
        # Start processing
        await asyncio.gather(receive_from_twilio(), send_to_twilio()) 