# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/go/dockerfile-reference/

# Debian Buster (the previous base) is end-of-life and its apt repos are gone, so it can no longer build
FROM python:3.12-slim-bookworm

# Install system dependencies including poppler-utils for PDF processing
RUN apt-get update && apt-get install -y \
    poppler-utils \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for temporary receipt storage
RUN mkdir -p data/temp_receipts

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=run.py

# Create a non-root user and switch to it
RUN useradd -m appuser
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Allow container healthchecks without installing curl
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

# Run with Gunicorn for production stability
# - 2 workers for handling concurrent requests
# - 120s timeout for long-running receipt processing
# - Auto-restart workers after 1000 requests to prevent memory leaks
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--max-requests", "1000", "--max-requests-jitter", "50", "--access-logfile", "-", "--error-logfile", "-", "run:app"]
