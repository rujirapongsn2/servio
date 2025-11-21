# Scripts

This directory contains utility scripts for testing various integrations.

## Gemini File Search Test

Test script for Google's Gemini File Search API that allows you to upload documents and query them using natural language.

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Add your Gemini API key to the `.env` file in the project root:

```bash
GEMINI_API_KEY=your_api_key_here
```

### Usage

#### Full-Featured Test Script

```bash
# Basic usage
python test_gemini_file_search.py --file document.pdf --query "What are the main findings?"

# Use a specific model
python test_gemini_file_search.py \
  --file report.pdf \
  --query "Summarize the key points" \
  --model gemini-2.0-flash-exp

# Keep the store after testing (don't auto-delete)
python test_gemini_file_search.py \
  --file data.pdf \
  --query "What does the document say about..." \
  --no-cleanup

# Quiet mode (minimal output)
python test_gemini_file_search.py \
  --file paper.pdf \
  --query "What is the methodology?" \
  --quiet

# Use API key from command line instead of .env
python test_gemini_file_search.py \
  --file document.pdf \
  --query "Summary?" \
  --api-key "your_key_here"
```

#### Simple Example Script

For a minimal quick-start example:

1. Edit `gemini_file_search_example.py` and set:
   - Your file path (line 23)
   - Your query (line 34)

2. Run:
```bash
python gemini_file_search_example.py
```

### Features

**test_gemini_file_search.py** includes:
- ✅ Command-line argument parsing
- ✅ Environment variable support
- ✅ Error handling and validation
- ✅ Upload progress tracking
- ✅ Grounding source extraction
- ✅ Automatic cleanup (optional)
- ✅ Configurable model selection
- ✅ Verbose and quiet modes

**gemini_file_search_example.py** is:
- 📝 Minimal quick-start example
- 🎯 Based on the original code structure
- 🚀 Simple to understand and modify

### Supported File Types

The Gemini File Search API supports various document formats including:
- PDF (.pdf)
- Text files (.txt)
- Word documents (.docx)
- And more...

### Available Models

**⚠️ IMPORTANT: File Search only works with Gemini 2.5 models**

Supported models:
- `gemini-2.5-flash` (default, recommended)
- `gemini-2.5-pro`
- See [Google AI models](https://ai.google.dev/models) for more options

❌ **NOT supported**: gemini-2.0-*, gemini-1.5-*, gemini-pro (older versions)

### Troubleshooting

**Invalid Argument Error (400 INVALID_ARGUMENT)**
- Error: "tools[0].tool_type: required one_of 'tool_type' must have one initialized field"
- **Cause**: Using a model that doesn't support File Search (only Gemini 2.5 models support it)
- **Solution**: Use `--model gemini-2.5-flash` or `--model gemini-2.5-pro`

**Rate Limit Errors (429 RESOURCE_EXHAUSTED)**
- Free tier has limited requests per minute
- Wait 60 seconds between requests
- Consider upgrading to paid tier for higher limits
- Monitor usage at: https://ai.dev/usage?tab=rate-limit

**Import Errors**
- Ensure you've installed dependencies: `pip install -r requirements.txt`
- If you get "cannot import name 'genai'", reinstall: `pip install --force-reinstall google-genai`

**File Upload Timeouts**
- Large files may take several minutes to process
- Use `--no-cleanup` to preserve the store if upload succeeds but query fails
- The script waits up to 5 minutes (300 seconds) by default

### API Reference

- [Gemini File Search Documentation](https://ai.google.dev/gemini-api/docs/file-search)
- [Google GenAI Python SDK](https://github.com/googleapis/python-genai)
- [Rate Limits Documentation](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Usage Monitor](https://ai.dev/usage?tab=rate-limit)
