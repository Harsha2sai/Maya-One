#!/bin/bash
# Force kill ports used by Maya Agent
# Try fuser first
fuser -k 5050/tcp > /dev/null 2>&1
fuser -k 8081/tcp > /dev/null 2>&1
fuser -k 8082/tcp > /dev/null 2>&1

# Fallback to lsof and kill -9 if they are still alive
echo "Cleaning ports 5050, 8081, 8082..."
lsof -t -i:5050 | xargs -r kill -9
lsof -t -i:8081 | xargs -r kill -9
lsof -t -i:8082 | xargs -r kill -9
sleep 1
exit 0
