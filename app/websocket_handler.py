import json
import base64
import asyncio
import websockets
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from app.config import OPENAI_API_KEY, ssl_context, LOG_EVENT_TYPES, VOICE, SYSTEM_MESSAGE, SHOW_TIMING_MATH
from app.utils import initialize_session, send_mark
from app.database import update_call_record, update_call_transcript
from app.database import supabase_client

async def handle_media_stream(websocket: WebSocket, transcript):
    print("Client connected")
    await websocket.accept()
    SHOW_TIMING_MATH = False
    current_call_sid = None
    current_twilio_call_sid = None
    current_simulation_id = None

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        },
        ssl=ssl_context
    ) as openai_ws:
        await initialize_session(openai_ws)

        # Connection specific state
        stream_sid = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None
        conversation_transcript = []  # Local transcript for this specific call

        async def receive_from_twilio():
            nonlocal stream_sid, latest_media_timestamp, current_call_sid, current_twilio_call_sid, current_simulation_id
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
                        current_twilio_call_sid = data['start'].get('callSid')
                        print(f"Stream started: {stream_sid}, Twilio Call SID: {current_twilio_call_sid}")
                        
                        # Fetch existing record and transcript
                        if current_twilio_call_sid:
                            try:
                                # First try to find by twilio_call_sid
                                result = supabase_client.table('voice_conversations')\
                                    .select('*')\
                                    .eq('twilio_call_sid', current_twilio_call_sid)\
                                    .execute()
                                
                                if result.data:
                                    record = result.data[0]
                                    current_simulation_id = record['simulation_id']
                                    current_call_sid = record['call_sid']
                                    if record.get('transcript'):
                                        conversation_transcript.extend(record['transcript'])
                                    print(f"Found existing record - Simulation ID: {current_simulation_id}, Call SID: {current_call_sid}")
                            except Exception as e:
                                print(f"Error fetching existing transcript: {str(e)}")
                                
                    elif data['event'] == 'mark':
                        if mark_queue:
                            mark_queue.pop(0)
                    elif data['event'] == "stop":
                        if openai_ws.open:
                            await openai_ws.close()
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()

        async def send_to_twilio():
            nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)

                    # Handle transcription completion
                    if response.get('type') == 'conversation.item.input_audio_transcription.completed':
                        user_transcript = response.get('transcript', '')
                        print(f"User input transcript: {user_transcript}")
                        if user_transcript.strip():  # Only add non-empty transcripts
                            transcript_entry = f"User: {user_transcript}"
                            conversation_transcript.append(transcript_entry)
                            
                            # Update database with new transcript
                            if current_call_sid and current_simulation_id:
                                try:
                                    await update_call_record(
                                        simulation_id=current_simulation_id,
                                        call_sid=current_call_sid,
                                        updates={"transcript": conversation_transcript}
                                    )
                                    print(f"Updated transcript for call {current_call_sid} in simulation {current_simulation_id}")
                                except Exception as e:
                                    print(f"Error updating transcript in database: {e}")

                    # Handle audio responses
                    elif response.get('type') == 'response.audio.delta' and 'delta' in response:
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

                        if response.get('item_id'):
                            last_assistant_item = response['item_id']

                        await send_mark(websocket, stream_sid)

                    # Handle assistant responses
                    elif response.get('type') == 'response.text.delta' and 'text' in response:
                        assistant_text = response['text']
                        transcript_entry = f"Assistant: {assistant_text}"
                        conversation_transcript.append(transcript_entry)
                        
                        # Update database with assistant response
                        if current_call_sid and current_simulation_id:
                            try:
                                await update_call_record(
                                    simulation_id=current_simulation_id,
                                    call_sid=current_call_sid,
                                    updates={"transcript": conversation_transcript}
                                )
                            except Exception as e:
                                print(f"Error updating transcript in database: {e}")

                    # Handle speech interruption
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        print("Speech started detected.")
                        if last_assistant_item:
                            print(f"Interrupting response with id: {last_assistant_item}")
                            await handle_speech_started_event()

            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

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

        await asyncio.gather(receive_from_twilio(), send_to_twilio()) 