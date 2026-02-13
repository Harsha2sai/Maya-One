import os
import pty
import sys
import time
import select
import subprocess
import re
import signal

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
LOG_FILE = "chaos_phase2_reports/exp5_runner.log"

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
            # print(data, end="") # Debugging
            if re.search(pattern, buffer, re.IGNORECASE):
                return True, buffer
    return False, buffer

def start_agent():
    pid, master_fd = pty.fork()
    if pid == 0:
        os.environ["PYTHONUNBUFFERED"] = "1"
        os.execvp(AGENT_CMD[0], AGENT_CMD)
    return pid, master_fd

def main():
    log("🚀 Starting Experiment 5: Process Kill (Crash Recovery)")
    os.makedirs("chaos_phase2_reports", exist_ok=True)

    # 1. Start Agent
    log("⏳ Starting first instance...")
    pid, master_fd = start_agent()
    
    try:
        # Wait for startup
        log("⏳ Waiting for agent startup (increased timeout for models)...")
        found, output = read_until(master_fd, "Listening", timeout=40)
        if not found:
            log(f"❌ Failed to start agent. Output: {output}")
            return

        # 2. Baseline
        log("🗣️ Phase 1: Baseline Check")
        time.sleep(2)
        os.write(master_fd, b"Hello\n")
        found, output = read_until(master_fd, "listening", timeout=15)
        log(f"Baseline Response: {output[-200:] if output else 'None'}")

        # 3. Kill Process
        log(f"🔥 Phase 2: Killing process {pid} with SIGKILL...")
        os.kill(pid, signal.SIGKILL)
        time.sleep(2)
        log("✅ Process killed.")

        # 4. Restart Agent
        log("⏳ Phase 3: Restarting agent...")
        new_pid, new_master_fd = start_agent()
        pid, master_fd = new_pid, new_master_fd # Update for finally block

        log("⏳ Waiting for agent restart (increased timeout for models)...")
        found, output = read_until(master_fd, "Listening", timeout=40)
        if not found:
            log(f"❌ Failed to restart agent. Output: {output}")
            return

        # 5. Recovery Check
        log("🗣️ Phase 4: Recovery Check (State Verification)")
        time.sleep(2)
        os.write(master_fd, b"I'm back, do you remember me?\n")
        # We check if it can still respond. True recovery would involve persistent memory.
        found, output = read_until(master_fd, "listening", timeout=20)
        log(f"Recovery Response: {output[-300:] if output else 'None'}")

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
