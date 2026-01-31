#!/usr/bin/env python3
"""
Debug script to check intent classification for a specific message
"""
import asyncio
import json
import os
import sys

# Add the server directory to the path
sys.path.insert(0, '/app')

from app.database import get_all_intent_rules

async def debug_intent_classification():
    """Debug the intent classification for the problematic message"""
    
    # The message from the screenshot
    test_message = "สวัสดีครับ วันนายคอนเสมาเนื้อหอมลิ้นฟ้าหาร์ม"
    
    print("=" * 80)
    print("INTENT CLASSIFICATION DEBUG")
    print("=" * 80)
    print(f"\nTest Message: {test_message}")
    print("\n" + "=" * 80)
    
    # 1. Check all configured intent rules
    print("\n1. CONFIGURED INTENT RULES:")
    print("-" * 80)
    
    try:
        rules = get_all_intent_rules()
        if not rules:
            print("⚠️  NO INTENT RULES CONFIGURED IN DATABASE")
        else:
            for i, rule in enumerate(rules, 1):
                print(f"\nRule #{i}:")
                print(f"  Group: {rule['group']}")
                print(f"  Color: {rule['color']}")
                print(f"  Keywords: {rule.get('keywords', [])}")
                print(f"  Description: {rule.get('description', 'N/A')}")
    except Exception as e:
        print(f"❌ Error fetching rules: {e}")
    
    # 2. Check keyword matching
    print("\n" + "=" * 80)
    print("2. KEYWORD MATCHING TEST:")
    print("-" * 80)
    
    try:
        rules = get_all_intent_rules()
        text_lower = test_message.lower().strip()
        print(f"\nSearching in: '{text_lower}'")
        
        matched = False
        for rule in rules:
            keywords = rule.get('keywords', [])
            if not keywords:
                continue
            
            for keyword in keywords:
                clean_keyword = keyword.lower().strip()
                if clean_keyword in text_lower:
                    print(f"\n✅ MATCH FOUND!")
                    print(f"   Keyword: '{keyword}'")
                    print(f"   Group: {rule['group']}")
                    print(f"   Color: {rule['color']}")
                    matched = True
                    break
            
            if matched:
                break
        
        if not matched:
            print("\n❌ NO KEYWORD MATCH - Will use AI classification")
    except Exception as e:
        print(f"❌ Error in keyword matching: {e}")
    
    # 3. Test AI classification
    print("\n" + "=" * 80)
    print("3. AI CLASSIFICATION TEST:")
    print("-" * 80)
    
    try:
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        system_prompt = """You are an expert real-time conversation monitor.
Analyze the latest exchange in the conversation and classify the user's current intent/behavior into exactly ONE of the following groups.

Groups and Definitions:
1. Smooth Resolution (Color: #2ECC71)
   - Prompt: Classify as Smooth Resolution when the customer responses indicate understanding, acceptance, or completion. The conversation progresses naturally, no repeated questions, sentiment is neutral or positive, and the issue can likely be resolved without human assistance.

2. Repetitive / Looping (Color: #F39C12)
   - Prompt: Classify as Repetitive / Looping when the customer asks the same or semantically similar question multiple times, shows repeated clarification requests, or the conversation does not progress despite multiple AI responses.

3. Confused / Unclear Intent (Color: #F1C40F)
   - Prompt: Classify as Confused / Unclear Intent when the customer's messages are vague, incomplete, unclear, or switch topics frequently, resulting in low intent confidence or difficulty determining the customer's actual goal.

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
        
        # Simulate the conversation history
        history = [
            {"role": "user", "content": test_message}
        ]
        
        print(f"\nSending to OpenAI GPT-4o-mini...")
        print(f"History: {json.dumps(history, ensure_ascii=False)}")
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(history, ensure_ascii=False)}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        print(f"\n✅ AI CLASSIFICATION RESULT:")
        print(f"   Group: {result.get('group')}")
        print(f"   Color: {result.get('color')}")
        print(f"\n   Raw Response: {result_text}")
        
    except Exception as e:
        print(f"❌ Error in AI classification: {e}")
    
    print("\n" + "=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(debug_intent_classification())
