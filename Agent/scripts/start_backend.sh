#!/bin/bash

# Navigate to Agent directory
cd "$(dirname "$0")/.."

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "❌ Virtual environment not found."
    exit 1
fi

echo "🚀 Starting Maya Agent (with integrated Token Server)..."

# Ensure clean slate
pkill -f "python agent.py" || true

# Run Agent (Token Server will auto-start)
python agent.py dev
