import os
import pty
import sys
import time
import select
import subprocess
import re
import json

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
LOG_FILE = "chaos_phase2_reports/exp6_runner.log"

def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def read_until(fd, pattern, timeout=15):
    buffer = ""
    start_time = time.time()
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
            if re.search(pattern, buffer, re.IGNORECASE):
                return True, buffer
    return False, buffer

def main():
    log("🚀 Starting Experiment 6: Persistence Failure (Database Unavailability)")
    os.makedirs("chaos_phase2_reports", exist_ok=True)

    # Enable Persistence Failure via environment
    chaos_config = {
        "enabled": True,
        "persistence_failure_rate": 1.0, # 100% failure for test
        "experiment_id": "exp_persistence_fail",
        "experiment_type": "infrastructure"
    }
    os.environ["AGENT_CHAOS_CONFIG"] = json.dumps(chaos_config)

    pid, master_fd = pty.fork()
    if pid == 0:
        os.environ["PYTHONUNBUFFERED"] = "1"
        os.execvp(AGENT_CMD[0], AGENT_CMD)

    try:
        log("⏳ Waiting for agent startup...")
        found, output = read_until(master_fd, "listening", timeout=40)
        if not found:
            log(f"❌ Failed to start agent. Output: {output}")
            return

        log("🗣️ Phase 1: Interaction during Persistence Failure")
        time.sleep(2)
        os.write(master_fd, b"Who am I?\n")
        
        # We expect it to FAIL memory retrieval but still respond using general knowledge
        found, output = read_until(master_fd, "listening", timeout=20)
        log(f"Agent Response: {output[-300:] if output else 'None'}")
        
        if "Simulated Chaos" in output or "failed" in output.lower() or "error" in output.lower():
             log("⚠️ ERROR logs detected in output (This is expected for internal failures)")
        
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
