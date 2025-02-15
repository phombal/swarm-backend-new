from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import logging
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self):
        self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    async def create_call(self, to: str, from_: str, url: str):
        """
        Create a new call using Twilio.
        """
        try:
            call = self.client.calls.create(
                to=to,
                from_=from_,
                url=url,
                record=True,
                status_callback=f"{url}/status-callback",
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                status_callback_method='POST'
            )
            logger.info(f"Created call with SID: {call.sid}")
            return call
        except TwilioRestException as e:
            logger.error(f"Twilio error: {str(e)}")
            raise

    async def end_call(self, call_sid: str):
        """
        End an active call.
        """
        try:
            call = self.client.calls(call_sid).update(status="completed")
            logger.info(f"Ended call with SID: {call_sid}")
            return call
        except TwilioRestException as e:
            logger.error(f"Error ending call {call_sid}: {str(e)}")
            raise

    async def get_call_status(self, call_sid: str):
        """
        Get the status of a call.
        """
        try:
            call = self.client.calls(call_sid).fetch()
            return call.status
        except TwilioRestException as e:
            logger.error(f"Error getting call status for {call_sid}: {str(e)}")
            raise 