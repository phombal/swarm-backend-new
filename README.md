# Stratify Testing Platform

A testing platform for simulating concurrent phone calls to test the Stratify voice agent using Twilio and OpenAI's Realtime API.

## Features

- Simulate multiple concurrent calls to test voice agent performance
- Configure custom test scenarios with specific conversation flows
- Real-time monitoring of test progress and results
- Detailed analytics and transcripts for each call
- Scalable architecture supporting hundreds of simultaneous calls
- Integration with Twilio for call handling
- Integration with OpenAI's Realtime API for voice processing

## Prerequisites

- Python 3.8+
- Twilio account with phone number
- OpenAI API key with access to Realtime API
- Supabase account for database
- Environment variables configured (see `.env.example`)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/stratify-testing-platform.git
cd stratify-testing-platform
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy the environment template and configure your variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Usage

1. Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

2. Create a test simulation:
```bash
curl -X POST http://localhost:8000/simulations/create \
  -H "Content-Type: application/json" \
  -d '{
    "target_phone": "+1234567890",
    "concurrent_calls": 5,
    "scenario": {
      "voice": "sage",
      "system_message": "You are a customer calling to place an order.",
      "max_turns": 10,
      "conversation_flow": [
        {"role": "user", "content": "I would like to place an order for delivery."},
        {"role": "assistant", "content": "I will help you with that. What would you like to order?"}
      ]
    }
  }'
```

3. Monitor simulation status:
```bash
curl http://localhost:8000/simulations/status/{simulation_id}
```

4. View simulation results:
```bash
curl http://localhost:8000/simulations/results/{simulation_id}
```

## API Documentation

Once the server is running, visit `http://localhost:8000/docs` for the complete API documentation.

## Environment Variables

- `TWILIO_ACCOUNT_SID`: Your Twilio Account SID
- `TWILIO_AUTH_TOKEN`: Your Twilio Auth Token
- `TWILIO_PHONE_NUMBER`: Your Twilio Phone Number
- `OPENAI_API_KEY`: Your OpenAI API Key
- `SUPABASE_URL`: Your Supabase Project URL
- `SUPABASE_KEY`: Your Supabase Project API Key
- `STRATIFY_BASE_URL`: Base URL of your Stratify instance
- `MAX_CONCURRENT_CALLS`: Maximum number of concurrent calls allowed
- `DEFAULT_MAX_TURNS`: Default maximum conversation turns
- `JWT_SECRET_KEY`: Secret key for JWT token generation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.