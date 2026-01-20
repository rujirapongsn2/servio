"""
LLM-Powered Conversation Enrichment Service
Analyzes conversations to extract insights, sentiment, topics, and quality metrics
"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio

from openai import AsyncOpenAI

from app import database


# Enrichment Analysis Prompt Template
ENRICHMENT_PROMPT = """You are an expert conversation analyst specializing in customer support interactions.

Analyze the following customer support conversation and provide detailed insights in JSON format.

CONVERSATION DATA:
{conversation_data}

METADATA:
- Duration: {duration_seconds} seconds
- Total Messages: {total_messages}
- Agents Involved: {agents_involved}
- Tools Used: {tools_used}

Please analyze this conversation and provide a comprehensive assessment in the following JSON structure:

{{
  "sentiment": {{
    "overall": "positive" | "neutral" | "negative",
    "score": <float between -1.0 and 1.0>,
    "explanation": "<brief explanation of sentiment in Thai language (ภาษาไทย)>"
  }},
  "topics": {{
    "primary": "product_inquiry" | "technical_support" | "billing" | "complaint" | "general_inquiry" | "order_management" | "other",
    "all": ["<topic1>", "<topic2>", ...]
  }},
  "quality": {{
    "resolution_quality": "excellent" | "good" | "fair" | "poor",
    "agent_performance_score": <float 0.0 to 1.0>,
    "response_clarity_score": <float 0.0 to 1.0>,
    "empathy_score": <float 0.0 to 1.0>,
    "explanation": "<brief quality assessment in Thai language (ภาษาไทย)>"
  }},
  "issues": {{
    "identified": ["<issue1 in Thai (ภาษาไทย)>", "<issue2 in Thai (ภาษาไทย)>", ...],
    "customer_pain_points": ["<pain_point1 in Thai (ภาษาไทย)>", "<pain_point2 in Thai (ภาษาไทย)>", ...],
    "suggestions": ["<improvement1 in Thai (ภาษาไทย)>", "<improvement2 in Thai (ภาษาไทย)>", ...]
  }},
  "business_intelligence": {{
    "customer_intent": "purchase" | "support" | "inquiry" | "complaint" | "feedback",
    "urgency_level": "critical" | "high" | "medium" | "low",
    "follow_up_needed": true | false,
    "follow_up_reason": "<reason in Thai (ภาษาไทย) if follow-up needed, null otherwise>"
  }}
}}

IMPORTANT: All text explanations, descriptions, issues, identified points, and suggestions MUST be written in Thai language (ภาษาไทย).

Focus on:
1. Accurate sentiment detection (consider context, not just keywords)
2. Precise topic classification
3. Fair quality assessment based on resolution and agent behavior
4. Actionable insights and suggestions
5. Business-relevant intelligence

Return ONLY the JSON object, no additional text.
"""


class EnrichmentService:
    """Service for enriching conversations with LLM analysis"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o-mini"  # Cost-effective model for analysis
        self.version = "v1.0"

    async def enrich_conversation(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        """
        Enrich a conversation with LLM analysis

        Args:
            conversation_id: ID of the conversation to analyze

        Returns:
            Dictionary with enrichment results, or None if failed
        """
        try:
            # Set status to processing
            database.update_enrichment_status(conversation_id, 'processing')
            
            # Prepare conversation data
            conversation_data = database.get_conversation_messages(conversation_id)
            if not conversation_data:
                print(f"No messages found for conversation {conversation_id}")
                database.update_enrichment_status(conversation_id, 'failed')
                return None

            # Get conversation metadata directly from conversations table (PostgreSQL)
            conn = database.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM conversations WHERE id = %s",
                (conversation_id,)
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                print(f"No conversation found for ID {conversation_id}")
                database.update_enrichment_status(conversation_id, 'failed')
                return None

            # RealDictCursor returns dict-like rows
            conversation = dict(row)

            # Format conversation for analysis
            formatted_conversation = self._format_conversation(conversation_data)

            # Create enrichment prompt
            prompt = ENRICHMENT_PROMPT.format(
                conversation_data=formatted_conversation,
                duration_seconds=conversation.get('duration_seconds', 0),
                total_messages=conversation.get('total_messages', 0),
                agents_involved=conversation.get('agents_involved', '[]'),
                tools_used=conversation.get('tools_used', '[]')
            )

            # Call LLM for analysis
            print(f"🤖 Analyzing conversation {conversation_id} with {self.model}...")
            analysis = await self._call_llm(prompt)

            if not analysis:
                print(f"❌ LLM analysis failed for conversation {conversation_id}")
                database.update_enrichment_status(conversation_id, 'failed')
                return None

            # Parse and validate response
            parsed = self._parse_analysis(analysis)
            if not parsed:
                print(f"❌ Failed to parse analysis for conversation {conversation_id}")
                database.update_enrichment_status(conversation_id, 'failed')
                return None

            # Save to database
            self._save_enrichment(conversation_id, parsed)
            
            # Set status to completed
            database.update_enrichment_status(conversation_id, 'completed')

            print(f"✅ Successfully enriched conversation {conversation_id}")
            return parsed

        except Exception as e:
            print(f"❌ Error enriching conversation {conversation_id}: {e}")
            database.update_enrichment_status(conversation_id, 'failed')
            return None

    def _format_conversation(self, messages: list) -> str:
        """Format conversation messages for LLM analysis"""
        formatted = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            agent_name = msg.get('agent_name')

            if agent_name:
                formatted.append(f"[{role.upper()} - {agent_name}]: {content}")
            else:
                formatted.append(f"[{role.upper()}]: {content}")

        return "\n".join(formatted)

    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Call OpenAI API for analysis"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a conversation analysis expert. Respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for consistent analysis
                response_format={"type": "json_object"}  # Ensure JSON response
            )

            return response.choices[0].message.content

        except Exception as e:
            print(f"❌ LLM API call failed: {e}")
            return None

    def _parse_analysis(self, analysis_json: str) -> Optional[Dict[str, Any]]:
        """Parse and validate LLM analysis response"""
        try:
            data = json.loads(analysis_json)

            # Validate required fields exist
            required_sections = ['sentiment', 'topics', 'quality', 'issues', 'business_intelligence']
            for section in required_sections:
                if section not in data:
                    print(f"❌ Missing required section: {section}")
                    return None

            return data

        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON: {e}")
            return None
        except Exception as e:
            print(f"❌ Validation error: {e}")
            return None

    def _save_enrichment(self, conversation_id: int, analysis: Dict[str, Any]):
        """Save enrichment results to database"""
        try:
            # Extract values from nested structure
            sentiment = analysis.get('sentiment', {})
            topics = analysis.get('topics', {})
            quality = analysis.get('quality', {})
            issues = analysis.get('issues', {})
            bi = analysis.get('business_intelligence', {})

            # Prepare analytics data dict for database
            analytics_data = {
                'overall_sentiment': sentiment.get('overall'),
                'sentiment_score': sentiment.get('score'),
                'sentiment_explanation': sentiment.get('explanation'),
                'primary_topic': topics.get('primary'),
                'topics': topics.get('all', []),
                'resolution_quality': quality.get('resolution_quality'),
                'agent_performance_score': quality.get('agent_performance_score'),
                'response_clarity_score': quality.get('response_clarity_score'),
                'empathy_score': quality.get('empathy_score'),
                'issues_identified': issues.get('identified', []),
                'customer_pain_points': issues.get('customer_pain_points', []),
                'suggestions': issues.get('suggestions', []),
                'customer_intent': bi.get('customer_intent'),
                'urgency_level': bi.get('urgency_level'),
                'follow_up_needed': bi.get('follow_up_needed', False),
                'follow_up_reason': bi.get('follow_up_reason'),
                'llm_model': self.model,
                'analysis_version': self.version
            }

            # Save to conversation_analytics table
            database.save_conversation_analytics(
                conversation_id=conversation_id,
                analytics_data=analytics_data
            )

            print(f"💾 Saved enrichment data for conversation {conversation_id}")

        except Exception as e:
            print(f"❌ Failed to save enrichment: {e}")
            raise


# Singleton instance
_enrichment_service = None


def get_enrichment_service() -> EnrichmentService:
    """Get the enrichment service singleton"""
    global _enrichment_service
    if _enrichment_service is None:
        _enrichment_service = EnrichmentService()
    return _enrichment_service
