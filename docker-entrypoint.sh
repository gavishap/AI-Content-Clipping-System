#!/bin/bash
set -e

echo "Starting bgutil PO token server (port 4416)..."
if [ -f /opt/bgutil/server/build/main.js ]; then
    node /opt/bgutil/server/build/main.js &
    BGUTIL_PID=$!
    sleep 3

    if kill -0 $BGUTIL_PID 2>/dev/null; then
        echo "bgutil server running (PID $BGUTIL_PID)"
    else
        echo "WARNING: bgutil server failed to start, continuing without it"
    fi
else
    echo "WARNING: bgutil server not found, skipping"
fi

echo "Verifying runtimes..."
echo "  node: $(node --version 2>/dev/null || echo 'NOT FOUND')"
echo "  deno: $(deno --version 2>/dev/null | head -1 || echo 'NOT FOUND')"
echo "  ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 || echo 'NOT FOUND')"

echo "Starting Nick Matau Clipper worker..."
exec python -m src.worker
