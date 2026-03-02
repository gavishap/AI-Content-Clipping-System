FROM python:3.11-slim

# System deps: ffmpeg for clip extraction, git for pip packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install extra deps not in requirements.txt yet
RUN pip install --no-cache-dir \
    gspread \
    google-auth \
    google-auth-oauthlib \
    google-api-python-client \
    sentence-transformers

# Copy all project files
COPY src/ src/
COPY prompts/ prompts/
COPY main.py .
COPY nick_voiceprint.json .

# Create work directory
RUN mkdir -p /tmp/clipper_work

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV WORK_DIR=/tmp/clipper_work
ENV VOICEPRINT_PATH=/app/nick_voiceprint.json

CMD ["python", "-m", "src.worker"]
