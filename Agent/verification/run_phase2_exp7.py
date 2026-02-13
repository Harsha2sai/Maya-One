import os
import pty
import sys
import time
import select
import subprocess
import re
import json

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
LOG_FILE = "chaos_phase2_reports/exp7_runner.log"

def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def read_until(fd, pattern, timeout=30):
    buffer = ""
    start_time = time.time()
    # Pattern to strip ANSI escape codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    while time.time() - start_time < timeout:
        r, _, _ = select.select([fd], [], [], 0.1)
        if fd in r:
            try:
                data = os.read(fd, 1024).decode(errors="ignore")
            except OSError:
                break
            if not data:
                break
            buffer += data
            # Strip ANSI codes for matching
            clean_buffer = ansi_escape.sub('', buffer)
            if re.search(pattern, clean_buffer, re.IGNORECASE):
                return True, buffer
    return False, buffer

def main():
    log("🚀 Starting Experiment 7: Long Real Session (30-turn stress test)")
    os.makedirs("chaos_phase2_reports", exist_ok=True)

    # Disable all faults for stability baseline
    os.environ["AGENT_CHAOS_CONFIG"] = json.dumps({"enabled": False})
    os.environ["HF_HUB_OFFLINE"] = "1"

    pid, master_fd = pty.fork()
    if pid == 0:
        os.environ["PYTHONUNBUFFERED"] = "1"
        os.execvp(AGENT_CMD[0], AGENT_CMD)

    try:
        log("⏳ Waiting for agent startup (increased timeout for models)...")
        found, output = read_until(master_fd, "shortcuts", timeout=180)
        if not found:
            log(f"❌ Failed to start agent. Output: {output[-500:] if output else 'None'}")
            return

        queries = [
            "Hello", "How are you?", "What time is it?", "Tell me a joke",
            "What's the weather?", "Who won the world cup?", "Remind me to drink water",
            "What was our first message?", "What's 2+2?", "Tell me about space",
            "Do you like music?", "What's the capital of France?", "Set an alarm for 8am",
            "List my alarms", "Delete the alarm", "Create a note: Chaos is fun",
            "Read my last note", "What's the meaning of life?", "Are you okay?",
            "Can you help me with coding?", "What's Python?", "Give me a recipe for cookies",
            "Tell me about LiveKit", "How does STT work?", "What is deep learning?",
            "Suggest a movie", "What's your name?", "Where are you hosted?",
            "Talk to me in French", "Goodbye"
        ]

        for i, query in enumerate(queries):
            log(f"🗣️ Turn {i+1}/30: Sending '{query}'")
            os.write(master_fd, f"{query}\n".encode())
            
            # Look for the prompt appearing again
            found, output = read_until(master_fd, "shortcuts", timeout=60)
            if not found:
                log(f"❌ Timeout/Crash at turn {i+1}. Partial output: {output[-500:] if output else 'None'}")
                break
            log(f"✅ Received response for turn {i+1}")

        log("🏁 Experiment Complete")

    except Exception as e:
        log(f"❌ Exception: {e}")
    finally:
        log("Cleaning up...")
        try:
            os.close(master_fd)
        except: pass
        if pid:
            try: os.kill(pid, 9)
            except: pass

if __name__ == "__main__":
    main()
