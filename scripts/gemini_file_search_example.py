#!/usr/bin/env python3
"""
Simple example of Gemini File Search usage.

This is a minimal, quick-start example based on your provided code.
For a more robust implementation with CLI args and error handling,
see test_gemini_file_search.py
"""

import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Initialize client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Create a file search store
print("Creating file search store...")
store = client.file_search_stores.create()
print(f"Store created: {store.name}")

# Upload a file to the store
print("\nUploading file...")
upload_op = client.file_search_stores.upload_to_file_search_store(
    file_search_store_name=store.name,
    file='path/to/your/document.pdf'  # ← Change this to your file path
)

# Wait for upload to complete
while not upload_op.done:
    print("  Waiting for upload to complete...")
    time.sleep(5)
    upload_op = client.operations.get(upload_op)

print("✓ Upload complete!")

# Query the document
print("\nQuerying document...")
response = client.models.generate_content(
    model='gemini-2.5-flash',  # Note: File Search only works with Gemini 2.5 models
    contents='What does the research say about ...',  # ← Change this query
    config=types.GenerateContentConfig(
        tools=[types.Tool(
            file_search=types.FileSearch(
                file_search_store_names=[store.name]
            )
        )]
    )
)

# Print response
print("\n" + "="*80)
print("RESPONSE:")
print("="*80)
print(response.text)
print("="*80)

# Get grounding sources
grounding = response.candidates[0].grounding_metadata
if not grounding:
    print('\n⚠️  No grounding sources found')
else:
    sources = {c.retrieved_context.title for c in grounding.grounding_chunks}
    print('\n📚 Sources:', *sources)

# Clean up (optional - comment out if you want to keep the store)
print(f"\nDeleting store {store.name}...")
client.file_search_stores.delete(name=store.name)
print("✓ Done!")
