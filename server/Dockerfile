# Multi-stage build for Python backend
FROM python:3.11-slim as base

# Install uv package manager
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
RUN uv sync --frozen

# Copy application code
COPY . .

# Create non-root user and setup data directory
RUN groupadd -g 1001 voiceagent && \
  useradd -u 1001 -g voiceagent -s /bin/sh voiceagent && \
  mkdir -p /app/data && \
  chmod -R 755 /app && \
  chown -R voiceagent:voiceagent /app

# Switch to non-root user
USER voiceagent

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run the application
CMD ["uv", "run", "--no-sync", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
