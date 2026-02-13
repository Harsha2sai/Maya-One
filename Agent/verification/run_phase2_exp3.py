import os
import pty
import sys
import time
import select
import subprocess
import re

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
# Fault scripts (manual execution required)
FAULT_SCRIPT = "sudo ./verification/faults/block_tts.sh"
RESTORE_SCRIPT = "sudo ./verification/faults/restore_tts.sh"
LOG_FILE = "chaos_phase2_reports/exp3_runner.log"

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
    log("🚀 Starting Experiment 3: TTS Provider Failure (Edge TTS)")
    
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
            log(f"⚠️  PLEASE RUN '{FAULT_SCRIPT}' THEN CREATE '{trigger_file}'")
            
            while not os.path.exists(trigger_file):
                time.sleep(1)
            log("✅ Fault Trigger Detected.")

            # 4. Test during outage
            log("🗣️ Phase 3: Testing during outage")
            # TTS failure might result in error logs but text should still print in console or at least not crash
            os.write(master_fd, b"Tell me a short joke\n")
            # We look for "listening" appearing again, indicating it finished "speaking" (or trying to)
            found, output = read_until(master_fd, "error|listening", timeout=20)
            log(f"Outage Response: {output[-200:] if output else 'None'}")

            # 5. Restore
            log("💊 Phase 4: Waiting for Restoration...")
            restore_trigger = "verification/faults/restore.trigger"
            log(f"⚠️  PLEASE RUN '{RESTORE_SCRIPT}' THEN CREATE '{restore_trigger}'")
            
            while not os.path.exists(restore_trigger):
                time.sleep(1)
            log("✅ Restore Trigger Detected.")

            # 6. Recovery
            log("🗣️ Phase 5: Recovery Check")
            time.sleep(5) 
            os.write(master_fd, b"Say something nice\n")
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
