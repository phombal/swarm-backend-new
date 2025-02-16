from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import logging
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, STRATIFY_BASE_URL

logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self):
        logger.info(f"Initializing TwilioService with account SID: {TWILIO_ACCOUNT_SID[:6]}...")
        logger.info(f"Using Twilio phone number: {TWILIO_PHONE_NUMBER}")
        logger.info(f"Using webhook base URL: {STRATIFY_BASE_URL}")
        self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    async def create_call(self, to: str, from_: str, url: str = None):
        """
        Create a new call using Twilio with media streaming enabled.
        """
        try:
            logger.info(f"Attempting to create streaming call to: {to} from: {from_}")
            
            # Create TwiML for streaming
            twiml = '''
                <?xml version="1.0" encoding="UTF-8"?>
                <Response>
                    <Start>
                        <Stream url="wss://your-server/media-stream" />
                    </Start>
                    <Connect>
                        <Stream url="wss://your-server/media-stream" />
                    </Connect>
                </Response>
            '''
            
            # Create call with streaming enabled
            call_params = {
                'to': to,
                'from_': from_,
                'twiml': twiml,
                'record': True,
                'statusCallback': 'https://your-server/status-callback',
                'statusCallbackEvent': ['initiated', 'ringing', 'answered', 'completed'],
                'statusCallbackMethod': 'POST'
            }
            
            call = self.client.calls.create(**call_params)
            
            logger.info(f"Successfully created streaming call with SID: {call.sid}")
            logger.info(f"Initial call status: {call.status}")
            return call
            
        except TwilioRestException as e:
            logger.error(f"Twilio error creating call: {str(e)}")
            logger.error(f"Error code: {e.code}")
            logger.error(f"Error message: {e.msg}")
            logger.error(f"More info: {e.more_info}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating call: {str(e)}", exc_info=True)
            raise

    async def end_call(self, call_sid: str):
        """
        End an active call.
        """
        try:
            logger.info(f"Attempting to end call with SID: {call_sid}")
            call = self.client.calls(call_sid).update(status="completed")
            logger.info(f"Successfully ended call with SID: {call_sid}")
            return call
        except TwilioRestException as e:
            logger.error(f"Twilio error ending call {call_sid}: {str(e)}")
            logger.error(f"Error code: {e.code}")
            logger.error(f"Error message: {e.msg}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error ending call: {str(e)}", exc_info=True)
            raise

    async def get_call_status(self, call_sid: str):
        """
        Get the status of a call.
        """
        try:
            logger.info(f"Fetching status for call SID: {call_sid}")
            call = self.client.calls(call_sid).fetch()
            logger.info(f"Call status: {call.status}")
            return call.status
        except TwilioRestException as e:
            logger.error(f"Twilio error getting call status for {call_sid}: {str(e)}")
            logger.error(f"Error code: {e.code}")
            logger.error(f"Error message: {e.msg}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting call status: {str(e)}", exc_info=True)
            raise 