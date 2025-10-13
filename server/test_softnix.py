"""
Test script for Softnix API integration
"""
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path="../.env")

from app.softnix_api import query_softnix_genai, SoftnixAPIError

def test_softnix_tool():
    """Test the Softnix API with a sample question"""
    question = "what products does Softnix offer?"

    print(f"🧪 Testing Softnix API")
    print(f"Question: {question}")
    print("-" * 80)

    try:
        result = query_softnix_genai(question)
        print(f"\n✅ Success!")
        print(f"\nAnswer:\n{result}")
        return True
    except SoftnixAPIError as e:
        print(f"\n❌ Error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_softnix_tool()
    exit(0 if success else 1)
