#!/bin/bash
for i in {1..3}
do
  source venv/bin/activate
  echo "Run $i"
  # Run the agent in background
  python3 -u agent.py start > debug_agent_restart_$i.log 2>&1 &
  PID=$!
  echo "Agent started with PID $PID. Waiting 30s..."
  sleep 30
  echo "Stopping agent..."
  kill -SIGINT $PID
  wait $PID
  echo "Agent stopped. Cooling down..."
  sleep 5
done
echo "Restart test complete."
