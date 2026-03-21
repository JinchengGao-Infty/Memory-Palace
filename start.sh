#!/bin/bash
# Memory Palace startup script
cd /Users/link/Desktop/Memory-Palace
source backend/.venv/bin/activate

# Prevent system proxy from interfering with local connections
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost,::1"
unset all_proxy ALL_PROXY http_proxy HTTP_PROXY https_proxy HTTPS_PROXY

# Start REST API backend (port 8000, LAN accessible)
cd backend
python main.py &
BACKEND_PID=$!

# Start MCP SSE server (port 8765)
HOST=0.0.0.0 PORT=8765 python run_sse.py &
SSE_PID=$!

echo "Memory Palace started: backend=$BACKEND_PID, mcp_sse=$SSE_PID"
wait
