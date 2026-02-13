#!/bin/bash
# Restore LLM Access
echo "restoring fault: unblocking api.groq.com..."
sudo sed -i '/api.groq.com/d' /etc/hosts
echo "Fault restored."
