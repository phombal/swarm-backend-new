# Swarm Voice AI Testing Platform - Backend

A sophisticated voice call platform that enables thousands of current AI-powered phone conversations using OpenAI's GPT-4, Twilio for telephony, and Supabase for data storage. The platform supports configurable AI behaviors, batch calling, and detailed conversation analysis.

## Features

- **AI-Powered Conversations**: Utilizes OpenAI's GPT-4 for natural, context-aware conversations
- **Configurable AI Behavior**: Customize accent, industry context, speaking pace, and more
- **Batch Call Support**: Make multiple calls simultaneously with controlled batching
- **Real-time Transcription**: Capture and store conversation transcripts
- **Conversation Analysis**: Detailed analysis of call quality, metrics, and performance
- **WebSocket Integration**: Real-time audio streaming and processing
- **Database Integration**: Persistent storage of call records and analytics

## Prerequisites

- Python 3.8+
- OpenAI API Key
- Twilio Account (Account SID and Auth Token)
- Supabase Account (URL and API Key)
- SSL Certificate for WebSocket connections

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables in `.env`:
```env
OPENAI_API_KEY=your_openai_api_key
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

## Usage

### Starting the Server

```bash
uvicorn app.main:app --reload
```

### Making a Test Call

```bash
curl -X POST "https://your-domain/test-call?to_number=+1234567890"
```

### Making Batch Calls

```bash
curl -X POST "https://your-domain/batch-test-calls?to_number=+1234567890&num_calls=2"
```

### Making Large Batch Calls (with controlled execution)

```bash
curl -X POST "https://your-domain/execute_large_calls?to_number=+1234567890&total_calls=4"
```

### Checking Call Status

```bash
curl "https://your-domain/batch-status"
```

### Getting Call Transcript

```bash
curl "https://your-domain/transcript?call_sid=CAXXXXXXXXXXXXXXX"
```

## Configuration

### Test Configuration Schema

The platform supports customizing AI behavior through test configurations:

```json
{
  "accent_types": ["neutral", "British", "American"],
  "industry": ["restaurant", "retail", "healthcare"],
  "speaking_pace": ["slow", "medium", "fast"],
  "emotion_types": ["professional", "friendly", "empathetic"],
  "background_noise": ["quiet", "moderate", "busy"],
  "max_turns": [5, 10, 15],
  "complexity_level": ["simple", "moderate", "complex"],
  "prompt_template": ["custom instruction templates"]
}
```

## Analysis Metrics

The platform provides detailed analysis of each conversation, including:

- Quality Metrics (coherence, task completion, context retention)
- Technical Metrics (latency, token usage, memory usage)
- Industry-Specific Metrics (order accuracy, required clarifications)
- Semantic Analysis (intent classification, entity extraction)

## Error Handling

The platform includes comprehensive error handling and logging:
- Call status monitoring
- WebSocket connection management
- Database operation verification
- API response validation

## Security

- All API keys and sensitive data should be stored in environment variables
- SSL/TLS encryption for WebSocket connections
- Supabase authentication for database access

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Your License Here]

## Support

For support, please [create an issue](your-issue-tracker-url) or contact [your-contact-info].
