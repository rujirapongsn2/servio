#!/usr/bin/env python3
"""Test script to verify agent and tool loading"""

import sys
sys.path.insert(0, '/Users/rujirapongair/myapp/openai-voice-agent-sdk-sample/server')

from app import database
from app.agent_config import build_agent_from_db, get_tool_by_name
import json

print("=" * 60)
print("Testing Agent and Tool Loading")
print("=" * 60)

# Get all agents from database
agents_data = database.get_all_agents()
print(f"\nFound {len(agents_data)} agents in database:")

for agent_data in agents_data:
    print(f"\n{'=' * 60}")
    print(f"Agent: {agent_data['name']} (ID: {agent_data['id']})")
    print(f"Model: {agent_data['model']}")
    print(f"Instructions: {agent_data['instructions'][:100]}...")
    print(f"Is Starting Agent: {agent_data.get('is_starting_agent', False)}")

    # Check tools
    print(f"\nTools ({len(agent_data.get('tools', []))}):")
    for tool_data in agent_data.get('tools', []):
        print(f"  - Tool ID: {tool_data['id']}")
        print(f"    Name: {tool_data['name']}")
        print(f"    Type: {tool_data['type']}")
        if tool_data.get('config'):
            config = json.loads(tool_data['config'])
            print(f"    Config Type: {config.get('type', 'N/A')}")
            print(f"    Description: {config.get('description', 'N/A')[:80]}...")

            # Test tool loading
            tool_instance = get_tool_by_name(tool_data['name'], config)
            if tool_instance:
                tool_name = getattr(tool_instance, '__name__', getattr(tool_instance, 'name', 'unknown'))
                tool_doc = getattr(tool_instance, '__doc__', 'N/A')
                print(f"    ✓ Tool loaded successfully: {tool_name}")
                print(f"    ✓ Tool docstring: {tool_doc[:80] if tool_doc else 'N/A'}...")
            else:
                print(f"    ✗ Failed to load tool")

    # Try to build the agent
    try:
        agent = build_agent_from_db(agent_data)
        print(f"\n✓ Agent built successfully")
        print(f"  - Agent name: {agent.name}")
        print(f"  - Number of tools: {len(agent.tools)}")
        print(f"  - Tools: {[t.__name__ for t in agent.tools]}")
    except Exception as e:
        print(f"\n✗ Failed to build agent: {str(e)}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("Test completed")
print("=" * 60)
