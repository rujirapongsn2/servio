"""
Gemini File Search Service

This module provides a service class for interacting with Google's Gemini File Search API.
It handles creating file search stores, uploading files, querying documents, and cleanup.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from google import genai
from google.genai import types


# MIME type mappings for common file extensions
MIME_TYPES = {
    # Documents
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
    '.md': 'text/markdown',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.odt': 'application/vnd.oasis.opendocument.text',
    '.ods': 'application/vnd.oasis.opendocument.spreadsheet',
    '.odp': 'application/vnd.oasis.opendocument.presentation',
    # Text formats
    '.rtf': 'application/rtf',
    '.csv': 'text/csv',
    '.json': 'application/json',
    '.xml': 'application/xml',
    '.html': 'text/html',
    '.htm': 'text/html',
    # Code files
    '.py': 'text/x-python',
    '.js': 'text/javascript',
    '.ts': 'text/typescript',
    '.java': 'text/x-java',
    '.cpp': 'text/x-c++src',
    '.c': 'text/x-c',
    '.h': 'text/x-c',
    '.go': 'text/x-go',
    '.rs': 'text/x-rust',
}


def get_mime_type(file_path: str) -> str:
    """
    Get MIME type for a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        MIME type string, defaults to 'application/octet-stream' if unknown
    """
    extension = Path(file_path).suffix.lower()
    return MIME_TYPES.get(extension, 'application/octet-stream')


class GeminiFileSearchService:
    """Service for managing Gemini File Search operations"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        """
        Initialize the Gemini File Search service.

        Args:
            api_key: Google Gemini API key (if None, loads from environment)
            model: Model to use for generation (default: gemini-2.5-flash)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def create_store(self, display_name: str) -> Dict[str, Any]:
        """
        Create a new file search store.

        Args:
            display_name: Display name for the store

        Returns:
            Dictionary with store information:
            - store_id: Gemini store ID (e.g., "fileSearchStores/abc123")
            - display_name: Display name
        """
        store = self.client.file_search_stores.create(
            config={'display_name': display_name}
        )

        return {
            "store_id": store.name,
            "display_name": display_name
        }

    def upload_file(
        self,
        store_id: str,
        file_path: str,
        max_wait_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Upload a file to a file search store.

        Args:
            store_id: Gemini store ID
            file_path: Path to the file to upload
            max_wait_seconds: Maximum time to wait for upload completion

        Returns:
            Dictionary with upload information:
            - success: Boolean indicating success
            - filename: Original filename
            - upload_time: Time taken to upload (seconds)
            - error: Error message if failed

        Raises:
            FileNotFoundError: If file doesn't exist
            TimeoutError: If upload times out
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check if filename contains non-ASCII characters
        temp_file = None
        upload_path = path

        try:
            # Try to encode filename as ASCII
            path.name.encode('ascii')
        except UnicodeEncodeError:
            # Filename has non-ASCII characters, create temp copy with ASCII name
            temp_dir = tempfile.gettempdir()
            safe_filename = f"temp_upload_{int(time.time())}{path.suffix}"
            temp_file = Path(temp_dir) / safe_filename
            shutil.copy2(path, temp_file)
            upload_path = temp_file

        start_time = time.time()

        try:
            # Start upload operation
            # Note: mime_type is auto-detected by the SDK from file extension
            upload_op = self.client.file_search_stores.upload_to_file_search_store(
                file_search_store_name=store_id,
                file=str(upload_path)
            )

            # Wait for upload to complete
            while not upload_op.done:
                elapsed = time.time() - start_time
                if elapsed > max_wait_seconds:
                    raise TimeoutError(f"Upload timed out after {max_wait_seconds} seconds")

                time.sleep(2)
                upload_op = self.client.operations.get(upload_op)

            upload_time = time.time() - start_time

            return {
                "success": True,
                "filename": path.name,
                "upload_time": upload_time
            }

        except Exception as e:
            return {
                "success": False,
                "filename": path.name,
                "error": str(e)
            }

        finally:
            # Clean up temporary file if it was created
            if temp_file and temp_file.exists():
                temp_file.unlink()

    def query(
        self,
        store_id: str,
        query: str,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query documents in a file search store.

        Args:
            store_id: Gemini store ID
            query: Natural language query
            model: Model to use (uses default if not specified)

        Returns:
            Dictionary with query results:
            - response: Response text
            - grounding_sources: List of source document names
            - metadata: Additional metadata from Gemini
        """
        model_name = model or self.model

        try:
            # Generate content using file search tool
            response = self.client.models.generate_content(
                model=model_name,
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[
                        types.Tool(
                            file_search=types.FileSearch(
                                file_search_store_names=[store_id]
                            )
                        )
                    ]
                )
            )

            # Extract response text
            response_text = response.text if response.text else "No response generated"

            # Extract grounding sources
            sources = []
            grounding = response.candidates[0].grounding_metadata if response.candidates else None

            if grounding and grounding.grounding_chunks:
                sources = list({
                    chunk.retrieved_context.title
                    for chunk in grounding.grounding_chunks
                    if hasattr(chunk, 'retrieved_context') and chunk.retrieved_context
                })

            return {
                "response": response_text,
                "grounding_sources": sources,
                "metadata": {
                    "model": model_name,
                    "candidates_count": len(response.candidates) if response.candidates else 0,
                    "has_grounding": bool(grounding)
                }
            }

        except Exception as e:
            return {
                "response": f"Error querying documents: {str(e)}",
                "grounding_sources": [],
                "metadata": {"error": str(e)}
            }

    def delete_store(self, store_id: str) -> bool:
        """
        Delete a file search store.

        Args:
            store_id: Gemini store ID

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.client.file_search_stores.delete(name=store_id)
            return True
        except Exception as e:
            print(f"Error deleting store {store_id}: {e}")
            return False

    def list_stores(self) -> List[Dict[str, Any]]:
        """
        List all file search stores.

        Returns:
            List of store dictionaries with store_id and display_name
        """
        try:
            stores = list(self.client.file_search_stores.list())
            return [
                {
                    "store_id": store.name,
                    "display_name": getattr(store, 'display_name', store.name)
                }
                for store in stores
            ]
        except Exception as e:
            print(f"Error listing stores: {e}")
            return []
