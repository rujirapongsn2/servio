"""
Test suite for LLM-powered conversation enrichment
"""
import asyncio
import json
from app.analytics_service import get_analytics_service
from app.enrichment_service import get_enrichment_service
from app import database


async def test_enrichment():
    """Test enrichment service with a real conversation"""
    print("🧪 Testing LLM Enrichment Service\n")
    print("=" * 70)

    # Get services
    analytics = get_analytics_service()
    enrichment = get_enrichment_service()

    # Test 1: Create a realistic customer support conversation
    print("\n✅ Test 1: Creating test conversation...")
    session_id = "enrichment-test-001"
    conversation_id = analytics.start_conversation(session_id)
    print(f"   Created conversation ID: {conversation_id}")

    # Simulate a realistic conversation
    print("\n✅ Test 2: Simulating customer support conversation...")

    # User: Initial complaint
    analytics.track_message(
        role="user",
        content="Hi, I'm very frustrated. I ordered a product 2 weeks ago and it still hasn't arrived. This is unacceptable!",
        agent_name=None
    )

    # Agent: Empathetic response
    analytics.track_message(
        role="assistant",
        content="I sincerely apologize for the delay with your order. I completely understand your frustration. Let me look into this right away and find out what's happening.",
        agent_name="Customer Support Agent"
    )

    # Track tool call
    analytics.track_tool_call(
        tool_name="search_orders",
        arguments={"customer_email": "customer@example.com"}
    )

    # Agent: Follow-up with information
    analytics.track_message(
        role="assistant",
        content="I've found your order #12345. I can see it's been delayed due to a shipping issue. I'm going to expedite this for you right now and upgrade you to express shipping at no extra cost. You should receive it within 2 business days.",
        agent_name="Customer Support Agent"
    )

    # User: Satisfied response
    analytics.track_message(
        role="user",
        content="Thank you so much! I really appreciate you helping me out and the free upgrade. That's great customer service.",
        agent_name=None
    )

    # Agent: Closing
    analytics.track_message(
        role="assistant",
        content="You're very welcome! I've sent you a confirmation email with the tracking details. Is there anything else I can help you with today?",
        agent_name="Customer Support Agent"
    )

    # User: Final response
    analytics.track_message(
        role="user",
        content="No, that's all. Thank you again!",
        agent_name=None
    )

    print("   ✓ Simulated 7 messages (4 user, 3 agent)")
    print("   ✓ Tracked 1 tool call")

    # End conversation
    print("\n✅ Test 3: Ending conversation...")
    await analytics.end_conversation(outcome="resolved")
    print("   ✓ Conversation ended")

    # Wait a moment for async enrichment to complete
    print("\n⏳ Waiting for LLM enrichment to complete...")
    await asyncio.sleep(8)  # Give time for the background task and LLM API call

    # Test 4: Verify enrichment was saved
    print("\n✅ Test 4: Checking enrichment results...")
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM conversation_analytics WHERE conversation_id = ?",
        (conversation_id,)
    )
    enrichment_data = cursor.fetchone()
    conn.close()

    if enrichment_data:
        print("   ✓ Enrichment data found!")
        print(f"\n   📊 Analysis Results:")
        print(f"   ─────────────────────────────────────────────────────")

        # Convert to dict for easier access
        columns = [
            'id', 'conversation_id', 'overall_sentiment', 'sentiment_score',
            'sentiment_explanation', 'primary_topic', 'topics',
            'resolution_quality', 'agent_performance_score',
            'response_clarity_score', 'empathy_score',
            'issues_identified', 'customer_pain_points', 'suggestions',
            'customer_intent', 'urgency_level', 'follow_up_needed',
            'follow_up_reason', 'analyzed_at', 'llm_model', 'analysis_version'
        ]
        data = dict(zip(columns, enrichment_data))

        # Sentiment Analysis
        print(f"\n   🎭 SENTIMENT ANALYSIS:")
        print(f"      Overall: {data['overall_sentiment']}")
        print(f"      Score: {data['sentiment_score']}")
        print(f"      Explanation: {data['sentiment_explanation']}")

        # Topic Classification
        print(f"\n   📁 TOPIC CLASSIFICATION:")
        print(f"      Primary Topic: {data['primary_topic']}")
        topics_list = json.loads(data['topics']) if data['topics'] else []
        print(f"      All Topics: {', '.join(topics_list)}")

        # Quality Metrics
        print(f"\n   ⭐ QUALITY METRICS:")
        print(f"      Resolution Quality: {data['resolution_quality']}")
        print(f"      Agent Performance: {data['agent_performance_score']}/1.0")
        print(f"      Response Clarity: {data['response_clarity_score']}/1.0")
        print(f"      Empathy Score: {data['empathy_score']}/1.0")

        # Issues & Insights
        print(f"\n   🔍 ISSUES & INSIGHTS:")
        issues = json.loads(data['issues_identified']) if data['issues_identified'] else []
        if issues:
            print(f"      Issues Identified:")
            for issue in issues:
                print(f"         • {issue}")

        pain_points = json.loads(data['customer_pain_points']) if data['customer_pain_points'] else []
        if pain_points:
            print(f"      Customer Pain Points:")
            for point in pain_points:
                print(f"         • {point}")

        suggestions = json.loads(data['suggestions']) if data['suggestions'] else []
        if suggestions:
            print(f"      Improvement Suggestions:")
            for suggestion in suggestions:
                print(f"         • {suggestion}")

        # Business Intelligence
        print(f"\n   💼 BUSINESS INTELLIGENCE:")
        print(f"      Customer Intent: {data['customer_intent']}")
        print(f"      Urgency Level: {data['urgency_level']}")
        print(f"      Follow-up Needed: {data['follow_up_needed']}")
        if data['follow_up_reason']:
            print(f"      Follow-up Reason: {data['follow_up_reason']}")

        # Metadata
        print(f"\n   🤖 METADATA:")
        print(f"      LLM Model: {data['llm_model']}")
        print(f"      Analysis Version: {data['analysis_version']}")
        print(f"      Analyzed At: {data['analyzed_at']}")

        print(f"\n   ─────────────────────────────────────────────────────")
        print("\n   ✅ Enrichment completed successfully!")

    else:
        print("   ❌ No enrichment data found!")
        print("   This could mean:")
        print("      1. The LLM enrichment is still in progress (try waiting longer)")
        print("      2. The enrichment failed (check logs above)")
        print("      3. No OPENAI_API_KEY is set")

    # Test 5: Manual enrichment test
    print("\n✅ Test 5: Testing manual enrichment...")
    print("   Creating second test conversation...")

    session_id_2 = "enrichment-test-002"
    conversation_id_2 = analytics.start_conversation(session_id_2)

    analytics.track_message(
        role="user",
        content="What are your business hours?",
        agent_name=None
    )

    analytics.track_message(
        role="assistant",
        content="We're open Monday to Friday, 9 AM to 6 PM EST.",
        agent_name="Coordinator Agent"
    )

    await analytics.end_conversation(outcome="completed")

    print("   ⏳ Running manual enrichment...")
    result = await enrichment.enrich_conversation(conversation_id_2)

    if result:
        print("   ✓ Manual enrichment succeeded!")
        print(f"   Sentiment: {result['sentiment']['overall']}")
        print(f"   Primary Topic: {result['topics']['primary']}")
    else:
        print("   ❌ Manual enrichment failed")

    print("\n" + "=" * 70)
    print("\n🎉 Enrichment testing complete!\n")


if __name__ == "__main__":
    asyncio.run(test_enrichment())
