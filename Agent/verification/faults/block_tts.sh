#!/bin/bash
# Inject TTS Outage by blocking Edge TTS DNS
echo "injecting fault: blocking speech.platform.bing.com..."
if ! grep -q "127.0.0.1 speech.platform.bing.com" /etc/hosts; then
    echo "127.0.0.1 speech.platform.bing.com" | sudo tee -a /etc/hosts > /dev/null
    echo "Fault injected."
else
    echo "Fault already active."
fi
