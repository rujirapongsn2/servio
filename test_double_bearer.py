import requests
import os
import json

def test():
    # Use the key from env (which is raw key)
    api_key = os.getenv("SOFTNIX_API_KEY")
    # Simulate DB having "Bearer " prefix
    db_token = f"Bearer {api_key}" 
    
    url = "https://genai.softnix.ai/external/api/chat-messages"
    
    payload = {
        "query": "Hello",
        "inputs": {},
        "files": [], 
        "citation": True, 
        "response_mode": "blocking"
    }
    
    # Simulate agent_config.py adding another "Bearer "
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {db_token}" 
    }
    
    print(f"Auth Header: {headers['Authorization']}")

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
