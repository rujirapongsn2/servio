#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini File Search Tool Test Script

This script demonstrates how to use Google's Gemini File Search API to:
1. Create a file search store (with optional custom name)
2. Upload documents to the store
3. Query the documents using natural language
4. Get grounded responses with source citations
5. List and reuse existing file search stores

Usage:
    # Create new store and query
    python test_gemini_file_search.py --file path/to/document.pdf --query "What does the document say about..."

    # Create named store and keep it for reuse
    python test_gemini_file_search.py --file doc.pdf --query "Summarize" --store-name "My Documents" --no-cleanup

    # List all existing stores
    python test_gemini_file_search.py --list-stores

    # Reuse existing store (no file upload needed)
    python test_gemini_file_search.py --use-store "fileSearchStores/abc123" --query "What about..."

Requirements:
    pip install google-genai python-dotenv
"""

import argparse
import mimetypes
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# Set UTF-8 encoding for stdout/stderr to handle non-ASCII characters
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from google import genai
from google.genai import types


class GeminiFileSearchTester:
    """Test harness for Gemini File Search functionality"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        """
        Initialize the Gemini File Search tester.

        Args:
            api_key: Google Gemini API key (if None, loads from environment)
            model: Model to use for generation (default: gemini-2.5-flash)
                   Note: File Search only works with Gemini 2.5 models
        """
        # Load environment variables from .env file
        load_dotenv()

        # Get API key from parameter or environment
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not found. Please set it in .env file or pass as parameter."
            )

        self.model = model
        self.client = genai.Client(api_key=self.api_key)
        self.store = None

    def list_file_search_stores(self) -> list:
        """List all available file search stores"""
        print("📋 Listing file search stores...")
        stores = list(self.client.file_search_stores.list())
        if stores:
            print(f"✓ Found {len(stores)} store(s):")
            for i, store in enumerate(stores, 1):
                print(f"  {i}. {store.name}")
        else:
            print("  No stores found")
        return stores

    def use_existing_store(self, store_name: str) -> None:
        """
        Use an existing file search store.

        Args:
            store_name: Name of the existing store to use
        """
        print(f"🔍 Loading existing store: {store_name}")
        try:
            self.store = self.client.file_search_stores.get(name=store_name)
            print(f"✓ Store loaded successfully: {self.store.name}")
        except Exception as e:
            raise ValueError(f"Store '{store_name}' not found: {e}")

    def create_file_search_store(self, display_name: Optional[str] = None) -> None:
        """
        Create a new file search store.

        Args:
            display_name: Optional display name for the store
        """
        print("📦 Creating file search store...")
        if display_name:
            self.store = self.client.file_search_stores.create(
                config={'display_name': display_name}
            )
            print(f"✓ File search store created: {self.store.name} (Display: {display_name})")
        else:
            self.store = self.client.file_search_stores.create()
            print(f"✓ File search store created: {self.store.name}")

    def upload_file(self, file_path: str, max_wait_seconds: int = 300) -> None:
        """
        Upload a file to the file search store.

        Args:
            file_path: Path to the file to upload
            max_wait_seconds: Maximum time to wait for upload completion
        """
        if not self.store:
            raise RuntimeError("File search store not created. Call create_file_search_store() first.")

        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            file_size_kb = path.stat().st_size / 1024
            print(f"📤 Uploading file: {path.name} ({file_size_kb:.2f} KB)")
        except UnicodeEncodeError:
            # Fallback for systems with encoding issues
            file_size_kb = path.stat().st_size / 1024
            print(f"📤 Uploading file ({file_size_kb:.2f} KB)")

        # Check if filename contains non-ASCII characters
        temp_file = None
        upload_path = path

        try:
            # Try to encode filename as ASCII
            path.name.encode('ascii')
        except UnicodeEncodeError:
            # Filename has non-ASCII characters, create temp copy with ASCII name
            print(f"  ⚠️  Filename contains non-ASCII characters, creating temporary copy...")
            temp_dir = tempfile.gettempdir()
            # Use original extension but ASCII filename
            safe_filename = f"temp_upload_{int(time.time())}{path.suffix}"
            temp_file = Path(temp_dir) / safe_filename
            shutil.copy2(path, temp_file)
            upload_path = temp_file
            print(f"  📋 Temporary file: {safe_filename}")

        # Start upload operation
        try:
            upload_op = self.client.file_search_stores.upload_to_file_search_store(
                file_search_store_name=self.store.name,
                file=str(upload_path)
            )
        except Exception as e:
            if temp_file and temp_file.exists():
                temp_file.unlink()  # Clean up temp file
            raise

        # Wait for upload to complete
        start_time = time.time()
        try:
            while not upload_op.done:
                elapsed = time.time() - start_time
                if elapsed > max_wait_seconds:
                    raise TimeoutError(f"Upload timed out after {max_wait_seconds} seconds")

                try:
                    print(f"  ⏳ Uploading... ({elapsed:.0f}s)")
                except UnicodeEncodeError:
                    print(f"  ⏳ Uploading... ({elapsed:.0f}s)".encode('utf-8', errors='replace').decode('utf-8'))
                time.sleep(5)
                upload_op = self.client.operations.get(upload_op)

            print(f"✓ File uploaded successfully in {time.time() - start_time:.1f}s")
        finally:
            # Clean up temporary file if it was created
            if temp_file and temp_file.exists():
                temp_file.unlink()
                print(f"  🗑️  Cleaned up temporary file")

    def query(self, question: str, verbose: bool = True) -> dict:
        """
        Query the file search store with a natural language question.

        Args:
            question: Natural language query
            verbose: Whether to print detailed output

        Returns:
            Dictionary containing response text and grounding sources
        """
        if not self.store:
            raise RuntimeError("File search store not created. Call create_file_search_store() first.")

        if verbose:
            print(f"\n❓ Query: {question}")
            print("🤖 Generating response...")

        # Generate content using file search tool
        response = self.client.models.generate_content(
            model=self.model,
            contents=question,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        file_search=types.FileSearch(
                            file_search_store_names=[self.store.name]
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

        if verbose:
            print("\n" + "=" * 80)
            print("📝 Response:")
            print("=" * 80)
            print(response_text)
            print("\n" + "=" * 80)

            if sources:
                print("📚 Grounding Sources:")
                print("=" * 80)
                for i, source in enumerate(sources, 1):
                    print(f"{i}. {source}")
            else:
                print("⚠️  No grounding sources found")
            print("=" * 80)

        return {
            "response": response_text,
            "sources": sources,
            "grounding_metadata": grounding
        }

    def cleanup(self) -> None:
        """Delete the file search store"""
        if self.store:
            print(f"\n🗑️  Deleting file search store: {self.store.name}")
            try:
                self.client.file_search_stores.delete(name=self.store.name)
                print("✓ File search store deleted")
            except Exception as e:
                print(f"⚠️  Error deleting store: {e}")


def main():
    """Main function for CLI usage"""
    parser = argparse.ArgumentParser(
        description="Test Gemini File Search Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search a PDF document (creates temporary store)
  python test_gemini_file_search.py --file document.pdf --query "What are the main findings?"

  # Create named store and keep it for reuse
  python test_gemini_file_search.py --file report.pdf --query "Summarize" --store-name "Project Reports" --no-cleanup

  # List all existing stores
  python test_gemini_file_search.py --list-stores

  # Query existing store (no file upload needed)
  python test_gemini_file_search.py --use-store "fileSearchStores/abc123" --query "What about Q2 results?"

  # Use a different model (must be Gemini 2.5)
  python test_gemini_file_search.py --file data.pdf --query "Analyze this" --model gemini-2.5-pro
        """
    )

    parser.add_argument(
        "--file",
        type=str,
        help="Path to the document file to upload (PDF, TXT, etc.)"
    )

    parser.add_argument(
        "--query",
        type=str,
        help="Natural language query to ask about the document"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini model to use (default: gemini-2.5-flash). Note: File Search only works with Gemini 2.5 models"
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="Gemini API key (if not set in .env file)"
    )

    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't delete the file search store after testing"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output (only show response and sources)"
    )

    parser.add_argument(
        "--store-name",
        type=str,
        help="Display name for the new file search store"
    )

    parser.add_argument(
        "--use-store",
        type=str,
        help="Use an existing file search store by name (e.g., fileSearchStores/abc123)"
    )

    parser.add_argument(
        "--list-stores",
        action="store_true",
        help="List all available file search stores and exit"
    )

    args = parser.parse_args()

    try:
        # Initialize tester
        tester = GeminiFileSearchTester(api_key=args.api_key, model=args.model)

        # Handle list-stores command
        if args.list_stores:
            tester.list_file_search_stores()
            return 0

        # Validate required arguments for query operations
        if not args.query:
            print("❌ Error: --query is required unless using --list-stores", file=sys.stderr)
            return 1

        # Use existing store or create new one
        if args.use_store:
            tester.use_existing_store(args.use_store)
        else:
            tester.create_file_search_store(display_name=args.store_name)

            # Upload file if creating new store
            if not args.file:
                print("❌ Error: --file is required when creating a new store", file=sys.stderr)
                return 1
            tester.upload_file(args.file)

        # Query
        result = tester.query(args.query, verbose=not args.quiet)

        # Cleanup unless disabled
        if not args.no_cleanup:
            tester.cleanup()
        else:
            print(f"\n💾 Store preserved: {tester.store.name}")

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
