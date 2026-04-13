# 🧩 Maya-One Plugin Skills & Authentication Guide

Welcome to the **Maya-One Plugin Architecture**! This guide explains how to set up, authenticate, and use the 15+ skills that have been added to your agent.

---

## 🚀 Quick Setup
To use these plugins, you first need to clone the external MCP repositories and then perform a one-time authentication.

### Step 1: Clone Repositories
Run the installer script to automatically download the necessary MCP servers:
```bash
cd Agent/plugins
python3 installer.py
```

### Step 2: Interactive Authentication
Many plugins (WhatsApp, Telegram, Google) require a **QR Code scan** or a **verification code** to connect to your personal account.

Use the `setup_auth.py` script to log in interactively:

#### 💬 WhatsApp (QR Code)
Run this and scan the QR code printed in your terminal with your phone:
```bash
python3 setup_auth.py whatsapp
```

#### ✈️ Telegram (Verification Code)
Enter your phone number and the code you receive in your Telegram app:
```bash
python3 setup_auth.py telegram
```

#### 📧 Google Workspace (Browser Login)
This will open a browser window for you to sign in:
```bash
python3 setup_auth.py google_workspace
```

---

## 🛠️ Plugin Categories & Features

### 💬 Messaging
- **WhatsApp**: Search/read messages, send text & media. (Requires Go bridge)
- **Telegram**: MTProto support for channels, groups, and personal chats.
- **Reddit**: Browse subreddits and search posts via PRAW.
- **Instagram**: Social search via XPOZ MCP.

### 🗂️ Google Workspace
- **Workspace**: Gmail + Calendar + Docs + Sheets in one.
- **Maps**: Official Google Maps search for Hyderabad and beyond.
- **Drive**: Search files and **auto-convert** docs to Markdown for the Maya RAG pipeline.

### 🎵 Media
- **Spotify**: Full playback and mood-based curation.
- **YouTube**: Transcript extraction and AI-powered video Q&A.

### 🎨 AI Generation
- **Fal.ai**: FLUX images, Veo 3 video, and MusicGen compute.
- **Video Agent**: Script ➔ Scenes ➔ Audio ➔ YouTube upload pipeline.

### 🏠 Smart Home
- **Home Assistant**: Control lights, locks, and climate via local SSE MCP.

### 🇮🇳 India Native (Custom)
- **PNR Status**: Check Indian Railways status.
- **UPI Payments**: Generate instant UPI payment links and QR data.
- **IRCTC**: Check train availability and initiate bookings.
- **TSRTC**: Get Telangana bus timings and seat info.

---

## 🛡️ Safety & Security
Maya-One implements a **Proxy Tool Pattern** for your security:
1. **Agent sees only the tool name**: It never interacts with the raw MCP protocol.
2. **SafetyGuard**: Enforces rate limits (e.g., 10 calls/min for Spotify).
3. **Confirmation Layer**: Sensitive tools (e.g., `send_whatsapp_message`) require user confirmation before execution.
4. **Local Adapters**: Custom `adapter.py` files allow you to intercept and modify tool behavior before it hits the network.

---

## 🔧 Troubleshooting
- **Missing npx**: Ensure you have Node.js installed to use `npx` plugins (Spotify, Brave, etc.).
- **Missing uv**: Ensure you have `uv` installed to use modern Python MCP plugins.
- **Port Conflicts**: Some plugins (like WhatsApp) require a local bridge running on a specific port. Ensure those are active if a plugin fails to connect.
