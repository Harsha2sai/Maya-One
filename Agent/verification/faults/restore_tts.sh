#!/bin/bash
# Restore TTS Access
echo "restoring fault: unblocking speech.platform.bing.com..."
sudo sed -i '/speech.platform.bing.com/d' /etc/hosts
echo "Fault restored."
