FROM python:3.11-slim

# System deps: ffmpeg, git, nodejs (required for bgutil PO token generator)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install latest yt-dlp (update regularly to stay ahead of YouTube bot detection)
RUN pip install --no-cache-dir --upgrade yt-dlp

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install extra deps
RUN pip install --no-cache-dir \
    gspread \
    google-auth \
    google-auth-oauthlib \
    google-api-python-client \
    sentence-transformers

# ─── BGUTIL PO TOKEN PROVIDER (bypasses YouTube bot detection) ───────────────
# Install the yt-dlp plugin that connects to the bgutil server
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

# Clone and build the bgutil server (Node.js server that generates PO tokens)
RUN git clone --depth 1 --branch 1.3.1 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    /opt/bgutil

RUN cd /opt/bgutil/server && npm ci && npx tsc
# ─────────────────────────────────────────────────────────────────────────────

# Copy all project files
COPY src/ src/
COPY prompts/ prompts/
COPY main.py .
COPY nick_voiceprint.json .

# Startup script: launch bgutil server in background, then start worker
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create work directory
RUN mkdir -p /tmp/clipper_work

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV WORK_DIR=/tmp/clipper_work
ENV VOICEPRINT_PATH=/app/nick_voiceprint.json

CMD ["/docker-entrypoint.sh"]
