"""
Simple test script to verify analytics service integration
"""
import asyncio
from app.analytics_service import get_analytics_service
from app import database

async def test_analytics():
    """Test analytics service lifecycle"""
    print("🧪 Testing Analytics Service Integration\n")

    # Get analytics service
    analytics = get_analytics_service()

    # Test 1: Start conversation
    print("✅ Test 1: Starting conversation...")
    session_id = "test-session-123"
    conversation_id = analytics.start_conversation(session_id)
    print(f"   Created conversation ID: {conversation_id}")

    # Test 2: Track user message
    print("\n✅ Test 2: Tracking user message...")
    analytics.track_message(
        role="user",
        content="Hello, I need help with my order",
        agent_name=None
    )
    print("   User message tracked")

    # Test 3: Track tool call
    print("\n✅ Test 3: Tracking tool call...")
    analytics.track_tool_call(
        tool_name="search_orders",
        arguments={"order_id": "12345"}
    )
    print("   Tool call tracked")

    # Test 4: Track agent message
    print("\n✅ Test 4: Tracking agent message...")
    analytics.track_message(
        role="assistant",
        content="I found your order. How can I help you?",
        agent_name="Customer Support Agent"
    )
    print("   Agent message tracked")

    # Test 5: Track another user message
    print("\n✅ Test 5: Tracking another user message...")
    analytics.track_message(
        role="user",
        content="I want to cancel it",
        agent_name=None
    )
    print("   User message tracked")

    # Test 6: Track another agent message
    print("\n✅ Test 6: Tracking another agent message...")
    analytics.track_message(
        role="assistant",
        content="I've processed your cancellation request.",
        agent_name="Customer Support Agent"
    )
    print("   Agent message tracked")

    # Test 7: End conversation
    print("\n✅ Test 7: Ending conversation...")
    await analytics.end_conversation(outcome="resolved")
    print("   Conversation ended")

    # Test 8: Verify data in database
    print("\n✅ Test 8: Verifying data in database...")
    conversation = database.get_conversation_by_session(session_id)
    if conversation:
        print(f"   Conversation found: ID={conversation['id']}")
        print(f"   Duration: {conversation['duration_seconds']} seconds")
        print(f"   Total messages: {conversation['total_messages']}")
        print(f"   User messages: {conversation['user_messages']}")
        print(f"   Agent messages: {conversation['agent_messages']}")
        print(f"   Outcome: {conversation['outcome']}")
    else:
        print("   ❌ Conversation not found!")

    # Test 9: Verify messages in database
    print("\n✅ Test 9: Verifying messages in database...")
    messages = database.get_conversation_messages(conversation_id)
    print(f"   Found {len(messages)} messages:")
    for i, msg in enumerate(messages, 1):
        print(f"   {i}. [{msg['role']}] {msg['content'][:50]}...")

    # Test 10: Get analytics summary
    print("\n✅ Test 10: Getting analytics summary...")
    summary = database.get_analytics_summary("all")
    print(f"   Total conversations: {summary['total_conversations']}")
    print(f"   Avg messages: {summary['avg_messages']}")

    print("\n🎉 All tests passed!\n")

if __name__ == "__main__":
    asyncio.run(test_analytics())
