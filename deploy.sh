#!/bin/bash
set -e

# Install dependencies
if command -v uv &> /dev/null; then
    echo "Installing dependencies with uv..."
    uv pip install -r requirements.txt -q
else
    echo "Installing dependencies with pip..."
    pip install -r requirements.txt -q
fi

echo "Starting server on port 8080..."

# Start server on port 8080 in background
nohup uvicorn app.main:app --host 0.0.0.0 --port 8080 > server.log 2>&1 &

# Wait a moment for server to start
sleep 2

# Check if server is running
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Server started successfully on port 8080"
    echo "PID: $(lsof -Pi :8080 -sTCP:LISTEN -t)"
else
    echo "Failed to start server. Check server.log for details."
    exit 1
fi
