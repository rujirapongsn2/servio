import requests
import os
import json

def test():
    api_key = os.getenv("SOFTNIX_API_KEY")
    if not api_key:
        print("SOFTNIX_API_KEY not set")
        return

    url = "https://genai.softnix.ai/external/api/chat-messages"
    
    # User's exact example structure (with empty files array since we don't have an ID)
    payload = {
        "query": "Hello, world!",
        "files": [], 
        "inputs": {},
        "citation": True,
        "response_mode": "blocking"
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    print(f"Sending payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        print("Success!")
        print(response.json())
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response text: {e.response.text}")

if __name__ == "__main__":
    test()
