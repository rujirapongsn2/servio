import json
import logging
import re
from typing import Optional
from openai import AsyncOpenAI
from app.model_settings import client_options, intent_model
from app.session_manager import session_manager
from app.intent_decision import classify_intent

from app.intent_contract import STANDARD_INTENT_GROUPS, INTENT_COLORS

INTENT_PRIORITY = {
    "Critical / Human Required": 0,
    "Frustrated / Escalating": 1,
    "Repetitive / Looping": 2,
    "Confused / Unclear Intent": 3,
    "Smooth Resolution": 4,
}
NEGATION = re.compile(r"ไม่|มิได้|อย่า|\b(?:no|not|never|without|cannot)\b|n't\b")
logger = logging.getLogger(__name__)

class IntentService:
    def __init__(self):
        self.client = AsyncOpenAI(**client_options("INTENT"))
        self.model = intent_model()

        
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

When multiple groups apply, prioritize Critical / Human Required, Frustrated / Escalating, Repetitive / Looping, Confused / Unclear Intent, then Smooth Resolution.
Respect explicit negation and the latest user message. Polite thanks do not mean an unresolved problem is solved.

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
            recent_history = history[-6:]
            
            if not recent_history:
                return

            # 1. Manual Keyword Check (Prioritized)
            manual_result = self._check_keywords(recent_history)
            if manual_result:
                await session_manager.update_session_intent(session_id, manual_result["group"], manual_result["color"])
                logger.info("Intent classification source=keywords")
                return

            decision_group = await classify_intent(recent_history)
            if decision_group is not None:
                await session_manager.update_session_intent(session_id, decision_group, INTENT_COLORS[decision_group])
                logger.info("Intent classification source=decision")
                return

            # 2. AI Analysis
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(recent_history, ensure_ascii=False)}
                ],
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            group = result.get("group")
            color = result.get("color")
            
            if group and color:
                await session_manager.update_session_intent(session_id, group, color)
                logger.info("Intent classification source=llm")
                
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
            if NEGATION.search(text):
                if re.search(r'''["'“”‘’]|คำว่า|แปลว่า|หมายถึง''', text):
                    return None
                configured_keywords = {
                    keyword.lower().strip()
                    for rule in rules
                    for keyword in rule.get("keywords", [])
                }
                negation_text = re.sub(r"ไม่มีปัญหาแล้ว(?:ครับ|ค่ะ)?[.!\s]*$", "", text)
                for phrase in ("ไม่พอใจ", "ไม่แน่ใจ", "ไม่เข้าใจ"):
                    if phrase in configured_keywords:
                        negation_text = negation_text.replace(phrase, "")
                # Negation outside these literal phrases still needs context.
                if NEGATION.search(negation_text):
                    return None
            for rule in sorted(rules, key=lambda rule: (
                INTENT_PRIORITY.get(rule["group"], len(INTENT_PRIORITY)), rule["group"],
            )):
                keywords = rule.get("keywords", [])
                if not keywords:
                    continue
                    
                for keyword in keywords:
                    clean_keyword = keyword.lower().strip()
                    if clean_keyword and clean_keyword in text:
                        return {"group": rule["group"], "color": rule["color"]}
        except Exception as e:
            print(f"Error checking keywords: {e}")
            
        return None

intent_service = IntentService()
