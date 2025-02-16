import json
import base64
import asyncio
import websockets
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from app.config import OPENAI_API_KEY, ssl_context, LOG_EVENT_TYPES, VOICE, SYSTEM_MESSAGE, SHOW_TIMING_MATH
from app.utils import initialize_session, send_mark
from app.database import update_call_record, update_call_transcript

async def handle_media_stream(websocket: WebSocket, transcript):
    print("Client connected")
    await websocket.accept()
    SHOW_TIMING_MATH = False
    current_call_sid = None  # Add this to track the current call

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
        conversation_transcript = []  # Add this to store the conversation

        async def receive_from_twilio():
            nonlocal stream_sid, latest_media_timestamp, current_call_sid
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.open:
                        latest_media_timestamp = int(
                            data['media']['timestamp'])
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        current_call_sid = data['start'].get('callSid')  # Get the call SID
                        print(f"Incoming stream has started {stream_sid}")
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
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()

        async def send_to_twilio():
            nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio, conversation_transcript
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)

                    # Handle transcription completion
                    if response.get('type') == 'conversation.item.input_audio_transcription.completed':
                        user_transcript = response.get('transcript', '')
                        print(f"User input transcript: {user_transcript}")
                        transcript_entry = f"User: {user_transcript}"
                        transcript.append(transcript_entry)
                        conversation_transcript.append(transcript_entry)
                        
                        # Update the database with the new transcript
                        if current_call_sid:
                            try:
                                await update_call_record(
                                    simulation_id="test_simulation",  # Using a test simulation ID for now
                                    call_sid=current_call_sid,
                                    updates={"conversation_transcript": conversation_transcript}
                                )
                                print(f"Updated database with new transcript for call {current_call_sid}")
                            except Exception as e:
                                print(f"Error updating transcript in database: {e}")

                    # Handle completed assistant responses
                    if response.get('type') == 'response.done':
                        response_data = response.get('response', {})
                        output = response_data.get('output', [])
                        for item in output:
                            if item.get('role') == 'assistant' and item.get('content'):
                                for content in item['content']:
                                    if content.get('type') == 'audio' and content.get('transcript'):
                                        assistant_text = content['transcript']
                                        print(f"Assistant response: {assistant_text}")
                                        transcript_entry = f"Assistant: {assistant_text}"
                                        transcript.append(transcript_entry)
                                        conversation_transcript.append(transcript_entry)
                                        
                                        # Update database with assistant response
                                        if current_call_sid:
                                            try:
                                                await update_call_record(
                                                    simulation_id="test_simulation",  # Using a test simulation ID for now
                                                    call_sid=current_call_sid,
                                                    updates={"conversation_transcript": conversation_transcript}
                                                )
                                                print(f"Updated database with assistant response for call {current_call_sid}")
                                            except Exception as e:
                                                print(f"Error updating transcript in database: {e}")

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
                            if SHOW_TIMING_MATH:
                                print(
                                    f"Setting start timestamp for new response: {response_start_timestamp_twilio}ms")

                        # Update last_assistant_item safely
                        if response.get('item_id'):
                            last_assistant_item = response['item_id']

                        await send_mark(websocket, stream_sid)

                    # Handle assistant responses for the transcript
                    if response.get('type') == 'response.text.delta' and 'text' in response:
                        assistant_text = response['text']
                        transcript.append(f"Assistant: {assistant_text}")
                        conversation_transcript.append(f"Assistant: {assistant_text}")
                        
                        # Update database with assistant response
                        if current_call_sid:
                            try:
                                await update_call_record(
                                    simulation_id="test_simulation",  # Using a test simulation ID for now
                                    call_sid=current_call_sid,
                                    updates={"conversation_transcript": conversation_transcript}
                                )
                            except Exception as e:
                                print(f"Error updating transcript in database: {e}")

                    # Trigger an interruption
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        print("Speech started detected.")
                        if last_assistant_item:
                            print(
                                f"Interrupting response with id: {last_assistant_item}")
                            await handle_speech_started_event()
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        async def handle_speech_started_event():
            nonlocal response_start_timestamp_twilio, last_assistant_item
            print("Handling speech started event.")
            if mark_queue and response_start_timestamp_twilio is not None:
                elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
                if SHOW_TIMING_MATH:
                    print(
                        f"Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms")

                if last_assistant_item:
                    if SHOW_TIMING_MATH:
                        print(
                            f"Truncating item with ID: {last_assistant_item}, Truncated at: {elapsed_time}ms")

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