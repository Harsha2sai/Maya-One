import os
import pty
import sys
import time
import select
import subprocess
import re

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
FAULT_CMD = ["./verification/faults/block_groq.sh"]
RESTORE_CMD = ["./verification/faults/restore_groq.sh"]
LOG_FILE = "chaos_phase2_reports/exp1_runner.log"

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
            # log(f"RAW: {data.strip()}") # Verbose
            if re.search(pattern, buffer, re.IGNORECASE):
                return True, buffer
    return False, buffer

def main():
    log("🚀 Starting Experiment 1: LLM Provider Outage")
    
    # Ensure log dir exists
    os.makedirs("chaos_phase2_reports", exist_ok=True)

    # Clean up any residual faults
    # subprocess.run(RESTORE_CMD, check=False) # Manual cleanup requires sudo

    pid, master_fd = pty.fork()

    if pid == 0:
        # Child: Run Agent
        # Set unbuffered
        os.environ["PYTHONUNBUFFERED"] = "1"
        os.execvp(AGENT_CMD[0], AGENT_CMD)
    else:
        # Parent
        try:
            log(f"Agent process started (PID: {pid})")
            
            # 1. Wait for startup
            log("⏳ Waiting for agent startup...")
            # Ideally wait for "Listening" or similar. Assuming 10s warmup.
            # Reading initial output
            found, output = read_until(master_fd, "Listening", timeout=15)
            # If "Listening" isn't printed by console mode yet (it might just be silent until input), just wait a bit.
            # Actually console mode usually prints intro.
            log(f"Startup output: {output[:200]}...")

            # 2. Baseline
            log("🗣️ Phase 1: Baseline Check")
            time.sleep(2)
            os.write(master_fd, b"Hello\n")
            found, output = read_until(master_fd, "listening", timeout=15) # Wait for it to finish speaking/listening again
            log(f"Baseline Response: {output[-200:] if output else 'None'}")
            
            # 3. Inject Fault
            log("🔥 Phase 2: Waiting for Fault Injection...")
            trigger_file = "verification/faults/fault.trigger"
            if os.path.exists(trigger_file):
                os.remove(trigger_file)
            
            # Wait for trigger
            log(f"⚠️  PLEASE RUN 'sudo ./verification/faults/block_groq.sh' THEN CREATE '{trigger_file}'")
            while not os.path.exists(trigger_file):
                time.sleep(1)
            log("✅ Fault Trigger Detected.")

            # 4. Test during outage
            log("🗣️ Phase 3: Testing during outage")
            os.write(master_fd, b"Tell me a joke\n")
            # Should hang or error.
            found, output = read_until(master_fd, "error|listening", timeout=20)
            log(f"Outage Response: {output[-200:] if output else 'None'}")
            
            # 5. Restore
            log("💊 Phase 4: Waiting for Restoration...")
            restore_trigger = "verification/faults/restore.trigger"
            if os.path.exists(restore_trigger):
                os.remove(restore_trigger)

            log(f"⚠️  PLEASE RUN 'sudo ./verification/faults/restore_groq.sh' THEN CREATE '{restore_trigger}'")
            while not os.path.exists(restore_trigger):
                time.sleep(1)
            log("✅ Restore Trigger Detected.")

            # 6. Recovery
            log("🗣️ Phase 5: Recovery Check")
            time.sleep(5) # Wait for network/sockets to clear
            os.write(master_fd, b"Are you there?\n")
            found, output = read_until(master_fd, "listening", timeout=20)
            log(f"Recovery Response: {output[-200:] if output else 'None'}")

            log("🏁 Experiment Complete")

        except Exception as e:
            log(f"❌ Exception: {e}")
        finally:
            log("Cleaning up...")
            # subprocess.run(RESTORE_CMD, check=False) # Manual cleanup needed
            os.close(master_fd)
            if pid: os.kill(pid, 9) # Kill agent

if __name__ == "__main__":
    main()
