import json
import os
from typing import Optional
from openai import AsyncOpenAI
from app.session_manager import session_manager

# Standard Intent Groups with default keywords (Thai + English)
STANDARD_INTENT_GROUPS = [
    {
        "group": "Smooth Resolution",
        "color": "#2ECC71",
        "description": "Customer shows understanding, acceptance, or completion",
        "default_keywords": ["ขอบคุณ", "เข้าใจแล้ว", "ได้เลย", "โอเค", "ชัดเจน", "thank you", "understood", "got it", "okay", "clear"]
    },
    {
        "group": "Repetitive / Looping",
        "color": "#F39C12",
        "description": "Customer asks same questions repeatedly",
        "default_keywords": ["อีกครั้ง", "ซ้ำ", "ไม่เข้าใจ", "บอกอีกที", "ยังไง", "again", "repeat", "still confused", "tell me again", "how"]
    },
    {
        "group": "Confused / Unclear Intent",
        "color": "#F1C40F",
        "description": "Customer's messages are vague or unclear",
        "default_keywords": ["งง", "สับสน", "ไม่แน่ใจ", "อาจจะ", "บางที", "confused", "unclear", "not sure", "maybe", "perhaps"]
    },
    {
        "group": "Frustrated / Escalating",
        "color": "#E74C3C",
        "description": "Customer expresses negative emotions or dissatisfaction",
        "default_keywords": ["หงุดหงิด", "รำคาญ", "ช้า", "ไม่พอใจ", "แย่", "frustrated", "annoyed", "slow", "dissatisfied", "terrible"]
    },
    {
        "group": "Critical / Human Required",
        "color": "#8E0E00",
        "description": "High-risk topics or explicit human assistance request",
        "default_keywords": ["คืนเงิน", "ทนาย", "ด่วน", "ร้องเรียน", "พูดกับคน", "refund", "lawyer", "urgent", "complaint", "speak to human"]
    }
]

class IntentService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o-mini"

        
        # Define the classification rules based on INTENT_MONITOR.md
        self.system_prompt = """You are an expert real-time conversation monitor.
Analyze the latest exchange in the conversation and classify the user's current intent/behavior into exactly ONE of the following groups.

Groups and Definitions:
1. Smooth Resolution (Color: #2ECC71)
   - Prompt: Classify as Smooth Resolution when the customer responses indicate understanding, acceptance, or completion. The conversation progresses naturally, no repeated questions, sentiment is neutral or positive, and the issue can likely be resolved without human assistance.

2. Repetitive / Looping (Color: #F39C12)
   - Prompt: Classify as Repetitive / Looping when the customer asks the same or semantically similar question multiple times, shows repeated clarification requests, or the conversation does not progress despite multiple AI responses.

3. Confused / Unclear Intent (Color: #F1C40F)
   - Prompt: Classify as Confused / Unclear Intent when the customer’s messages are vague, incomplete, unclear, or switch topics frequently, resulting in low intent confidence or difficulty determining the customer’s actual goal.

4. Frustrated / Escalating (Color: #E74C3C)
   - Prompt: Classify as Frustrated / Escalating when the customer expresses negative emotions, dissatisfaction, impatience, or irritation through wording, tone, punctuation, or shortened replies, indicating rising emotional tension.

5. Critical / Human Required (Color: #8E0E00)
   - Prompt: Classify as Critical / Human Required when the conversation involves high-risk topics, sensitive information, complaints, refunds, legal or policy issues, or when the customer explicitly requests human assistance.

Output JSON format only:
{
  "group": "Group Name",
  "color": "Hex Color"
}
"""

    async def analyze_and_update(self, session_id: str, history: list):
        """
        Analyze the conversation history and update the session with the detected intent.
        This is meant to be run as a background task.
        """
        try:
            # We only need the last few messages for real-time behavioral monitoring
            # Taking the last 6 messages (3 turns) is usually sufficient context
            recent_history = history[-6:] if len(history) > 6 else history
            
            if not recent_history:
                return

            # 1. Manual Keyword Check (Prioritized)
            manual_result = self._check_keywords(recent_history)
            if manual_result:
                await session_manager.update_session_intent(session_id, manual_result["group"], manual_result["color"])
                return

            # 2. AI Analysis
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(recent_history)}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            group = result.get("group")
            color = result.get("color")
            
            if group and color:
                await session_manager.update_session_intent(session_id, group, color)
                
        except Exception as e:
            print(f"Error in intent analysis for session {session_id}: {e}")

    def _check_keywords(self, history: list) -> Optional[dict]:
        """Check if the latest user message matches any defined keywords"""
        from app import database
        
        # Get latest user message
        # Use .get("role") to avoid KeyError if the history item (e.g. tool call) doesn't have a role
        last_user_msg = next((m for m in reversed(history) if m.get("role") == "user"), None)
        if not last_user_msg:
            return None
            
        text = last_user_msg.get("content", "").lower().strip()
        
        try:
            rules = database.get_all_intent_rules()
            for rule in rules:
                keywords = rule.get("keywords", [])
                if not keywords:
                    continue
                    
                for keyword in keywords:
                    clean_keyword = keyword.lower().strip()
                    if clean_keyword in text:
                        return {"group": rule["group"], "color": rule["color"]}
        except Exception as e:
            print(f"Error checking keywords: {e}")
            
        return None

intent_service = IntentService()
