import subprocess
import time
import sys
import os
import signal
import threading
from datetime import datetime

# Configuration
DURATION_SECONDS = 600  # 10 minutes
PING_INTERVAL = 60      # Send input every 60 seconds
AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
# AGENT_CMD = ["python3", "agent.py", "console"] # Adjust if needed

def log(msg):
    with open("verification/stability.log", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

def stream_reader(pipe, name, stop_event):
    """Reads output from a pipe and logs it."""
    try:
        with pipe:
            for line in iter(pipe.readline, b''):
                if stop_event.is_set():
                    break
                line_str = line.decode('utf-8', errors='replace').strip()
                if line_str:
                    with open("verification/stability.log", "a") as f:
                        f.write(f"[{name}] {line_str}\n")
    except ValueError:
        pass # Pipe closed

def run_stability_test():
    log(f"🚀 Starting Stability Run for {DURATION_SECONDS} seconds...")
    
    # optimize environment
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = os.getcwd()

    try:
        process = subprocess.Popen(
            AGENT_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Merge stderr into stdout for simplicity or keep separate
            env=env,
            # bufsize=0 # Removed to rely on default buffering
        )
    except Exception as e:
        log(f"❌ Failed to start agent process: {e}")
        return False

    stop_event = threading.Event()

    # Start readers
    stdout_thread = threading.Thread(target=stream_reader, args=(process.stdout, "AGENT_OUT", stop_event))
    stderr_thread = threading.Thread(target=stream_reader, args=(process.stderr, "AGENT_ERR", stop_event))
    stdout_thread.start()
    stderr_thread.start()

    start_time = time.time()
    
    try:
        while True:
            elapsed = time.time() - start_time
            remaining = DURATION_SECONDS - elapsed
            
            if remaining <= 0:
                log("✅ Stability run duration reached!")
                break
            
            if process.poll() is not None:
                log(f"❌ Agent crashed! Exit code: {process.returncode}")
                stop_event.set()
                return False

            # Valid liveness every interval
            if int(elapsed) % PING_INTERVAL == 0 and elapsed > 1:
                log("pinging agent...")
                try:
                    process.stdin.write(b"ping\n")
                    process.stdin.flush()
                except BrokenPipeError:
                    log("❌ Broken pipe when attempting to ping agent.")
                    break

            time.sleep(1)
            
    except KeyboardInterrupt:
        log("⚠️ Test interrupted by user.")
    finally:
        stop_event.set()
        if process.poll() is None:
            log("🛑 Terminating agent process...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        
    return True

if __name__ == "__main__":
    success = run_stability_test()
    sys.exit(0 if success else 1)
