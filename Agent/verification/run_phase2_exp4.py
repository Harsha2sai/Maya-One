import os
import pty
import sys
import time
import select
import subprocess
import re

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
# Fault scripts (manual execution required)
LOG_FILE = "chaos_phase2_reports/exp4_runner.log"

def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def read_until(fd, pattern, timeout=10):
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
    log("🚀 Starting Experiment 4: Internet Loss (Offline Survival)")
    
    os.makedirs("chaos_phase2_reports", exist_ok=True)

    # Clean up triggers from previous runs
    for t in ["verification/faults/fault.trigger", "verification/faults/restore.trigger"]:
        if os.path.exists(t):
            os.remove(t)

    pid, master_fd = pty.fork()

    if pid == 0:
        # Child
        os.environ["PYTHONUNBUFFERED"] = "1"
        os.execvp(AGENT_CMD[0], AGENT_CMD)
    else:
        # Parent
        try:
            log(f"Agent process started (PID: {pid})")
            
            # 1. Wait for startup
            log("⏳ Waiting for agent startup...")
            found, output = read_until(master_fd, "Listening", timeout=15)
            log(f"Startup output: {output[:200]}...")

            # 2. Baseline
            log("🗣️ Phase 1: Baseline Check")
            time.sleep(2)
            os.write(master_fd, b"Hello\n")
            found, output = read_until(master_fd, "listening", timeout=15)
            log(f"Baseline Response: {output[-200:] if output else 'None'}")
            
            # 3. Inject Fault
            log("🔥 Phase 2: Waiting for Fault Injection...")
            trigger_file = "verification/faults/fault.trigger"
            log(f"⚠️  PLEASE DISCONNECT INTERNET NOW (Unplug cable / Turn off Wi-Fi) THEN CREATE '{trigger_file}'")
            
            while not os.path.exists(trigger_file):
                time.sleep(1)
            log("✅ Fault Trigger Detected.")

            # 4. Test during outage
            log("🗣️ Phase 3: Testing during outage")
            # Without internet, STT/LLM/TTS will all fail. Verify process doesn't crash.
            os.write(master_fd, b"Can you hear me now?\n")
            # Expecting error logs or timeout, but process should stay alive
            found, output = read_until(master_fd, "error|listening", timeout=20)
            log(f"Outage Response: {output[-200:] if output else 'None'}")

            # 5. Restore
            log("💊 Phase 4: Waiting for Restoration...")
            restore_trigger = "verification/faults/restore.trigger"
            log(f"⚠️  PLEASE RECONNECT INTERNET NOW THEN CREATE '{restore_trigger}'")
            
            while not os.path.exists(restore_trigger):
                time.sleep(1)
            log("✅ Restore Trigger Detected.")

            # 6. Recovery
            log("🗣️ Phase 5: Recovery Check")
            log("⏳ Waiting 10s for network to stabilize...")
            time.sleep(10) 
            os.write(master_fd, b"Are we back online?\n")
            found, output = read_until(master_fd, "listening", timeout=20)
            log(f"Recovery Response: {output[-200:] if output else 'None'}")

            log("🏁 Experiment Complete")

        except Exception as e:
            log(f"❌ Exception: {e}")
        finally:
            log("Cleaning up...")
            os.close(master_fd)
            if pid: os.kill(pid, 9)

if __name__ == "__main__":
    main()
