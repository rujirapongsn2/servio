import requests
import os
import json

def test():
    api_key = os.getenv("SOFTNIX_API_KEY")
    url = "https://genai.softnix.ai/external/api/chat-messages"
    
    # Minimal payload (missing response_mode, citation, inputs, files)
    payload = {
        "query": "Hello",
        # Missing everything else
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Status: {e.response.status_code}")
             print(f"Response: {e.response.text}")

if __name__ == "__main__":
    test()
