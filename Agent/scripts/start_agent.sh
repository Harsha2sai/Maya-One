#!/bin/bash

# Maya Agent Quick Start Guide

echo "🎯 Maya Voice Assistant Agent"
echo "=============================="
echo ""

# Navigate to Agent directory
cd "$(dirname "$0")/.."

echo "📂 Working Directory: $(pwd)"
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Creating venv..."
    python3 -m venv venv
    echo "Installing dependencies..."
    ./venv/bin/pip install -r requirements.txt
fi

echo "✅ Virtual environment ready"
echo ""

# Start the agent
echo "🚀 Starting Maya Agent..."
echo "   - LLM: Groq (llama-3.3-70b-versatile)"
echo "   - STT: Deepgram (nova-2)"
echo "   - TTS: Edge-TTS (en-IN-NeerjaNeural - FREE)"
echo "   - Tools: Weather, Search, PC Control, System"
echo ""
echo "🎤 Ready for voice commands!"
echo "   Try: 'Open Firefox', 'What's the weather?', etc."
echo ""
echo "⏸️  Press Ctrl+C to stop"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run the agent
./venv/bin/python agent.py dev
