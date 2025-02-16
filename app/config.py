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
SYSTEM_MESSAGE = os.getenv("SYSTEM_MESSAGE", 
    "You are an AI assistant at a restaurant. Your role is to greet customers warmly, "
    "take their orders, answer questions about the menu, and provide helpful suggestions. "
    "Keep your responses friendly but concise. If a customer asks about specials, "
    "recommend our most popular dishes. After taking an order, always confirm the items "
    "ordered and provide an estimated preparation time."
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