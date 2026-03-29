#!/bin/bash
set -e

echo "Starting bgutil PO token server (port 4416)..."
node /opt/bgutil/server/build/main.js &
BGUTIL_PID=$!

# Give it a moment to start
sleep 2

echo "bgutil server running (PID $BGUTIL_PID)"
echo "Starting Nick Matau Clipper worker..."

exec python -m src.worker
