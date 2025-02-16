import os
import ssl
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Voice Configuration
DEFAULT_SYSTEM_MESSAGE = os.getenv("SYSTEM_MESSAGE", 
    "You are a customer calling Bella Roma Italian restaurant. You are interested in ordering "
    "Italian food for dinner. You should ask about the menu, specials, and popular dishes. "
    "You're particularly interested in authentic Italian cuisine and might ask about appetizers, "
    "main courses, and desserts. Be friendly but also somewhat indecisive, as you want to hear "
    "about different options before making your choice. You can ask about ingredients, preparation "
    "methods, and portion sizes. If you like what you hear, you'll eventually place an order."
)

# SSL Context for WebSocket connections
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Ensure required environment variables are set
required_vars = [
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "OPENAI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_KEY"
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}") 