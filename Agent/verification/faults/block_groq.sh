#!/bin/bash
# Inject LLM Outage by blocking Groq DNS
echo "injecting fault: blocking api.groq.com..."
if ! grep -q "127.0.0.1 api.groq.com" /etc/hosts; then
    echo "127.0.0.1 api.groq.com" | sudo tee -a /etc/hosts > /dev/null
    echo "Fault injected."
else
    echo "Fault already active."
fi
