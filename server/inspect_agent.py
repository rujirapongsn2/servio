import inspect
from agents import Agent

print("Agent Init Signature:")
print(inspect.signature(Agent.__init__))

print("\nAgent Docstring:")
print(Agent.__doc__)
