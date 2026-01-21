import inspect
import agents

print("Agents Module Contents:")
for name, obj in inspect.getmembers(agents):
    if inspect.isclass(obj):
        print(f"Class: {name}")

try:
    from agents.llm import LLM
    print("\nFound agents.llm.LLM")
    print(inspect.signature(LLM.__init__))
except ImportError:
    pass

try:
    from openai import OpenAI
    print("\nOpenAI Client Signature:")
    print(inspect.signature(OpenAI.__init__))
except ImportError:
    pass
