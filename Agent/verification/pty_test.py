import os
import pty
import time
import sys
import select
import subprocess

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]

def test_pty():
    # Create invalid master/slave pty pair
    master, slave = pty.openpty()
    
    # Start agent with slave as stdin/stdout/stderr
    p = subprocess.Popen(
        AGENT_CMD, 
        stdin=slave, 
        stdout=slave, 
        stderr=slave,
        cwd=os.getcwd(),
        env=os.environ.copy(),
        close_fds=True
    )
    
    os.close(slave) # Parent doesn't need slave
    
    print("Agent started with PID:", p.pid)
    
    # Read/Write loop
    buffer = b""
    try:
        # Give it time to start
        time.sleep(5)
        
        # Send "hello"
        print("Sending 'hello'...")
        os.write(master, b"hello\n")
        
        start = time.time()
        while time.time() - start < 10:
            r, _, _ = select.select([master], [], [], 0.1)
            if master in r:
                data = os.read(master, 1024)
                if not data:
                    break
                buffer += data
                # print("Chunk:", data.decode(errors='replace'))
                
    except OSError as e:
        print("Error:", e)
    finally:
        p.terminate()
        p.wait()
        os.close(master)

    print("--- Output Capture ---")
    print(buffer.decode(errors='replace')[:2000])

if __name__ == "__main__":
    test_pty()
