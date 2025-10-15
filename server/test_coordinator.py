#!/usr/bin/env python3
"""Test script to verify Coordinator Agent setup"""

import sys
sys.path.insert(0, '/Users/rujirapongair/myapp/openai-voice-agent-sdk-sample/server')

from app.agent_config import get_runtime_starting_agent

print("=" * 60)
print("Testing Coordinator Agent Setup")
print("=" * 60)

# Get the runtime starting agent (Coordinator)
coordinator = get_runtime_starting_agent()

print(f"\nStarting Agent: {coordinator.name}")
print(f"Model: {coordinator.model}")
print(f"Instructions:\n{coordinator.instructions}")

print(f"\n\nHandoffs ({len(coordinator.handoffs)}):")
for i, handoff in enumerate(coordinator.handoffs, 1):
    print(f"{i}. {handoff.name}")
    print(f"   - Model: {handoff.model}")
    print(f"   - Tools: {len(handoff.tools)} tool(s)")
    for tool in handoff.tools:
        tool_name = getattr(tool, 'name', 'unknown')
        print(f"     * {tool_name}")

print("\n" + "=" * 60)
print("Test completed")
print("=" * 60)
