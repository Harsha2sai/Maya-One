#!/bin/bash
# Restore STT Access
echo "restoring fault: unblocking api.deepgram.com..."
sudo sed -i '/api.deepgram.com/d' /etc/hosts
echo "Fault restored."
