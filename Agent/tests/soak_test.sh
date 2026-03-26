#!/bin/bash
# soak_test.sh - 24-Hour Voice Reconnect Stability Test

echo "🚀 Starting 24-Hour Soak Test..."
echo "WARNING: This script simulates network failures using iptables. Sudo access required."

# Trap Ctrl+C to cleanup
trap cleanup SIGINT SIGTERM

cleanup() {
    echo "🛑 Stopping Soak Test..."
    # Kill agent functionality
    pkill -f "python agent.py"
    # Ensure network rule is removed
    sudo iptables -D OUTPUT -p tcp --dport 443 -j DROP 2>/dev/null
    echo "✅ Cleanup complete."
    exit 0
}

# 1. Start Agent in background
echo "🎤 Starting Agent (Dev Mode)..."
python agent.py dev > agent_soak.log 2>&1 &
AGENT_PID=$!
echo "Agent PID: $AGENT_PID"

# Wait for startup
sleep 10

echo "⏳ Starting Chaos Loop (Press Ctrl+C to stop)..."
echo "Monitoring 'agent_soak.log' for activity..."

START_TIME=$(date +%s)
DURATION=$((24 * 3600)) # 24 hours

while [ $(($(date +%s) - START_TIME)) -lt $DURATION ]; do
    # Randomized generic wait (simulate normal operation)
    WAIT_TIME=$((RANDOM % 300 + 60)) # 1-6 minutes
    echo "✅ Normal operation for ${WAIT_TIME}s..."
    sleep $WAIT_TIME

    # Inject Network Failure
    echo "🔥 Simulating Network Instability (30s drop)..."
    sudo iptables -A OUTPUT -p tcp --dport 443 -j DROP
    
    # Wait during outage
    sleep 30
    
    # Restore Network
    echo "🔄 Restoring Network..."
    sudo iptables -D OUTPUT -p tcp --dport 443 -j DROP
    
    # Check if agent is still alive
    if ! kill -0 $AGENT_PID 2>/dev/null; then
        echo "❌ Agent CRASHED! Check agent_soak.log"
        break
    else
        echo "✅ Agent still running (PID: $AGENT_PID)"
    fi
    
    # Optional: Grep logs for health metrics
    tail -n 50 agent_soak.log | grep "🏥 System Health"
done

echo "🎉 Soak Test Completed!"
cleanup
