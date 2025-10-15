"""
Softnix GenAI API Client
API Documentation: https://genai.softnix.ai/external/api/chat-messages
"""

import os
import json
import requests
from typing import Optional


class SoftnixAPIError(Exception):
    """Custom exception for Softnix API errors"""
    pass


def query_softnix_genai(query: str, files: Optional[list] = None, inputs: Optional[dict] = None) -> str:
    """
    Query the Softnix GenAI API to get information about Softnix products/services.

    Args:
        query (str): The question or query to ask
        files (list, optional): List of file IDs to include. Defaults to None.
        inputs (dict, optional): Additional inputs. Defaults to None.

    Returns:
        str: Response from the Softnix GenAI API

    Raises:
        SoftnixAPIError: If the API request fails
    """
    # Get API key from environment variable
    api_key = os.getenv("SOFTNIX_API_KEY")
    if not api_key:
        raise SoftnixAPIError("SOFTNIX_API_KEY environment variable is not set")

    # API endpoint
    url = "https://genai.softnix.ai/external/api/chat-messages"

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Prepare request body
    # Allow optional extra inputs via env to adapt to server configuration without code changes
    extra_inputs_env = os.getenv("SOFTNIX_API_INPUTS", "")
    extra_inputs = {}
    if extra_inputs_env:
        try:
            extra_inputs = json.loads(extra_inputs_env)
        except Exception:
            extra_inputs = {}

    payload = {
        "query": query,
        "files": files or [],
        "inputs": {**(inputs or {}), **extra_inputs},
        "citation": True,
        "response_mode": "blocking"
    }

    try:
        # Make POST request
        print(f"🌐 Calling Softnix GenAI API with query: {query}")
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60  # 60 second timeout (API can take 30-40 seconds)
        )

        # Check for HTTP errors
        response.raise_for_status()

        # Parse JSON response
        data = response.json()

        # Extract the answer from response
        # Adjust this based on actual API response structure
        if "answer" in data:
            answer = data["answer"]
        elif "message" in data:
            answer = data["message"]
        elif "response" in data:
            answer = data["response"]
        else:
            # If structure is different, return the whole JSON as string
            answer = json.dumps(data, ensure_ascii=False)

        print(f"✅ Softnix API response received")
        return answer

    except requests.exceptions.Timeout:
        error_msg = "Softnix API request timed out after 60 seconds"
        print(f"❌ {error_msg}")
        raise SoftnixAPIError(error_msg)

    except requests.exceptions.ConnectionError:
        error_msg = "Failed to connect to Softnix API. Please check your internet connection."
        print(f"❌ {error_msg}")
        raise SoftnixAPIError(error_msg)

    except requests.exceptions.HTTPError as e:
        error_msg = f"Softnix API HTTP error: {e.response.status_code} - {e.response.text}"
        print(f"❌ {error_msg}")
        raise SoftnixAPIError(error_msg)

    except json.JSONDecodeError:
        error_msg = "Failed to parse Softnix API response as JSON"
        print(f"❌ {error_msg}")
        raise SoftnixAPIError(error_msg)

    except Exception as e:
        error_msg = f"Unexpected error calling Softnix API: {str(e)}"
        print(f"❌ {error_msg}")
        raise SoftnixAPIError(error_msg)


def test_softnix_api():
    """Test function to verify API connectivity"""
    try:
        result = query_softnix_genai("Hello, what services does Softnix provide?")
        print("Test successful!")
        print(f"Response: {result}")
        return True
    except SoftnixAPIError as e:
        print(f"Test failed: {e}")
        return False


if __name__ == "__main__":
    # For testing purposes
    from dotenv import load_dotenv
    load_dotenv(dotenv_path="../../.env")
    test_softnix_api()
