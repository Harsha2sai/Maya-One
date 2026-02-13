#!/bin/bash
# Inject STT Outage by blocking Deepgram DNS
echo "injecting fault: blocking api.deepgram.com..."
if ! grep -q "127.0.0.1 api.deepgram.com" /etc/hosts; then
    echo "127.0.0.1 api.deepgram.com" | sudo tee -a /etc/hosts > /dev/null
    echo "Fault injected."
else
    echo "Fault already active."
fi
