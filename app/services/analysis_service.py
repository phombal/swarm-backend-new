import json
import logging
from datetime import datetime
import openai
from typing import Dict, List
from app.database import supabase_client
from app.config import OPENAI_API_KEY
from uuid import UUID

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = '''You are an extremely precise and objective conversation analysis system. Your task is to analyze a conversation between a User and an Assistant in a restaurant ordering context, providing detailed metrics across multiple dimensions. You must be intensely scrutinizing and precise in your analysis.

Analyze the conversation and provide exact numerical values for the following metrics:

Quality Metrics (all values between 0 and 1):
- coherence_score: How logically connected and flowing is the conversation DECIMAL
- task_completion_score: How well was the primary task accomplished DECIMAL
- context_retention_score: How well context was maintained throughout DECIMAL
- natural_language_score: How natural and human-like was the language DECIMAL
- appropriateness_score: How appropriate were the responses DECIMAL
- engagement_score: How engaging was the conversation DECIMAL
- error_recovery_score: How well were errors or misunderstandings handled DECIMAL
- overall_quality_score: Overall quality assessment DECIMAL

Technical Metrics:
- avg_latency_ms: Average response time in milliseconds INTEGER
- min_latency_ms: Minimum response time in milliseconds INTEGER
- max_latency_ms: Maximum response time in milliseconds INTEGER
- p95_latency_ms: 95th percentile latency INTEGER
- total_tokens: Estimated total tokens used INTEGER
- tokens_per_message: Average tokens per message DECIMAL
- token_efficiency: Ratio of meaningful content to total tokens (0-1) DECIMAL
- memory_usage_mb: Estimated memory usage in MB INTEGER
- model_temperature: Temperature setting used for generation DECIMAL
- conversation_type: Type of conversation (e.g., "Restaurant Order") TEXT
- sentiment_score: Overall sentiment analysis (-1 to 1) DECIMAL
- message_type: Type of message (e.g., "order", "clarification", "confirmation") TEXT

Restaurant-Specific Metrics:
- order_accuracy: How accurately the order was captured (0-1) DECIMAL
- required_clarifications: Number of times clarification was needed INTEGER
- completion_time: Time taken to complete the order in seconds INTEGER
- menu_knowledge: Assistant's knowledge of menu items (0-1) DECIMAL
- special_requests: Number of special requests handled INTEGER
- upsell_attempts: Number of appropriate upsell attempts INTEGER

Semantic Analysis:
- intent_classification: Map of intents to confidence scores (0-1) JSONB
- entity_extraction: List of key entities identified (menu items, preferences, etc.) JSONB
- topic_classification: List of identified topics (e.g., "menu", "pricing", "allergies") TEXT[]
- semantic_role_labels: Map of semantic roles to values JSONB
- conversation_flow: List of conversation stages TEXT[]

Provide your analysis in valid JSON format with these exact field names and absolutely no other text. Ensure all numerical values match their specified data types (INTEGER or DECIMAL).'''

async def analyze_conversation(conversation_id: UUID, message_timestamps: List[Dict]) -> bool:
    """
    Analyze a conversation using GPT-4 and store results in the database.
    """
    try:
        # Format conversation for analysis
        conversation_text = format_conversation(message_timestamps)
        # Log the conversation text being analyzed
        logger.info("Analyzing conversation text:")
        logger.info(conversation_text)
        # Get GPT analysis
        analysis = await get_gpt_analysis(conversation_text)
        # Log the raw analysis output
        logger.info("Raw analysis output from GPT:")
        logger.info(json.dumps(analysis, indent=2))
        # Store results in database
        await store_analysis_results(conversation_id, analysis)
        
        return True
    except Exception as e:
        logger.error(f"Error analyzing conversation: {str(e)}")
        return False

def format_conversation(message_timestamps: List[Dict]) -> str:
    """Format the conversation for GPT analysis."""
    formatted_conversation = []
    for msg in message_timestamps:
        formatted_conversation.append(f"{msg['message']} [Timestamp: {msg['timestamp']}]")
    return "\n".join(formatted_conversation)

async def get_gpt_analysis(conversation_text: str) -> Dict:
    """Get analysis from GPT-4."""
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        logger.info("Sending conversation to OpenAI for analysis...")
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": ANALYSIS_PROMPT},
                    {"role": "user", "content": conversation_text}
                ],
                temperature=0.3
            )
        except openai.APIError as api_err:
            logger.error(f"OpenAI API Error: {str(api_err)}")
            raise
        except openai.APIConnectionError as conn_err:
            logger.error(f"OpenAI Connection Error: {str(conn_err)}")
            raise
        except openai.RateLimitError as rate_err:
            logger.error(f"OpenAI Rate Limit Error: {str(rate_err)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during OpenAI API call: {str(e)}")
            raise
            
        if not response.choices:
            logger.error("OpenAI response contains no choices")
            raise ValueError("Invalid response from OpenAI: no choices available")
            
        try:
            nested_analysis = json.loads(response.choices[0].message.content)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse OpenAI response as JSON: {str(json_err)}")
            logger.error(f"Raw response content: {response.choices[0].message.content}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error parsing OpenAI response: {str(e)}")
            raise
            
        # Flatten the nested structure
        analysis = {}
        
        # Extract Quality Metrics
        if "Quality Metrics" in nested_analysis:
            analysis.update(nested_analysis["Quality Metrics"])
            
        # Extract Technical Metrics
        if "Technical Metrics" in nested_analysis:
            analysis.update(nested_analysis["Technical Metrics"])
            
        # Extract Restaurant-Specific Metrics
        if "Restaurant-Specific Metrics" in nested_analysis:
            analysis.update(nested_analysis["Restaurant-Specific Metrics"])
            
        # Extract Semantic Analysis
        if "Semantic Analysis" in nested_analysis:
            analysis.update(nested_analysis["Semantic Analysis"])
            
        # Validate required fields are present
        required_fields = ['overall_quality_score', 'task_completion_score', 'order_accuracy']
        missing_fields = [field for field in required_fields if field not in analysis]
        if missing_fields:
            logger.error(f"Analysis response missing required fields: {missing_fields}")
            logger.error(f"Available fields: {list(analysis.keys())}")
            logger.error(f"Full nested response: {json.dumps(nested_analysis, indent=2)}")
            raise ValueError(f"Invalid analysis response: missing fields {missing_fields}")
        
        # Log the analysis results
        logger.info("OpenAI Analysis Results:")
        logger.info(f"Overall Quality Score: {analysis.get('overall_quality_score', 'N/A')}")
        logger.info(f"Task Completion Score: {analysis.get('task_completion_score', 'N/A')}")
        logger.info(f"Order Accuracy: {analysis.get('order_accuracy', 'N/A')}")
        logger.info(f"Required Clarifications: {analysis.get('required_clarifications', 'N/A')}")
        logger.info(f"Conversation Type: {analysis.get('conversation_type', 'N/A')}")
        logger.info(f"Sentiment Score: {analysis.get('sentiment_score', 'N/A')}")
        logger.info(f"Topics: {', '.join(analysis.get('topic_classification', []))}")
        
        return analysis
    except Exception as e:
        logger.error(f"Error getting GPT analysis: {str(e)}")
        raise

async def store_analysis_results(conversation_id: UUID, analysis: Dict) -> None:
    """Store analysis results in the database."""
    try:
        # Extract and store quality metrics
        quality_metrics = {
            "conversation_id": str(conversation_id),
            "coherence_score": analysis.get("coherence_score"),
            "task_completion_score": analysis.get("task_completion_score"),
            "context_retention_score": analysis.get("context_retention_score"),
            "natural_language_score": analysis.get("natural_language_score"),
            "appropriateness_score": analysis.get("appropriateness_score"),
            "engagement_score": analysis.get("engagement_score"),
            "error_recovery_score": analysis.get("error_recovery_score"),
            "overall_quality_score": analysis.get("overall_quality_score"),
            "order_accuracy": analysis.get("order_accuracy"),
            "required_clarifications": analysis.get("required_clarifications"),
            "completion_time": analysis.get("completion_time"),
            "menu_knowledge": analysis.get("menu_knowledge"),
            "special_requests": analysis.get("special_requests"),
            "upsell_attempts": analysis.get("upsell_attempts")
        }
        
        # Extract and store technical metrics
        technical_metrics = {
            "conversation_id": str(conversation_id),
            "avg_latency_ms": analysis.get("avg_latency_ms"),
            "min_latency_ms": analysis.get("min_latency_ms"),
            "max_latency_ms": analysis.get("max_latency_ms"),
            "p95_latency_ms": analysis.get("p95_latency_ms"),
            "total_tokens": analysis.get("total_tokens"),
            "tokens_per_message": analysis.get("tokens_per_message"),
            "token_efficiency": analysis.get("token_efficiency"),
            "memory_usage_mb": analysis.get("memory_usage_mb"),
            "model_temperature": analysis.get("model_temperature"),
            "conversation_type": analysis.get("conversation_type"),
            "sentiment_score": analysis.get("sentiment_score"),
            "message_type": analysis.get("message_type")
        }
        
        # Extract and store analysis results
        analysis_results = {
            "conversation_id": str(conversation_id),
            "intent_classification": analysis.get("intent_classification"),
            "entity_extraction": analysis.get("entity_extraction"),
            "topic_classification": analysis.get("topic_classification"),
            "semantic_role_labels": analysis.get("semantic_role_labels"),
            "conversation_flow": analysis.get("conversation_flow")
        }
        
        # Log before database operations
        logger.info("Storing analysis results in database...")
        
        # Insert into database tables
        supabase_client.table("quality_metrics").insert(quality_metrics).execute()
        logger.info("Stored quality metrics")
        
        supabase_client.table("technical_metrics").insert(technical_metrics).execute()
        logger.info("Stored technical metrics")
        
        supabase_client.table("analysis_results").insert(analysis_results).execute()
        logger.info("Stored analysis results")
        
    except Exception as e:
        logger.error(f"Error storing analysis results: {str(e)}")
        logger.error(f"Analysis data: {json.dumps(analysis, indent=2)}")
        raise 