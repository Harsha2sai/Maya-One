
import psutil
import time
import os
import datetime
import sys

def monitor(pid):
    try:
        proc = psutil.Process(pid)
        print(f"🔍 Monitoring PID {pid}...")
        print("Time, Memory(MB), Threads, FDs")
        
        while True:
            if not proc.is_running():
                print("❌ Process died")
                break
                
            mem_info = proc.memory_info()
            threads = proc.num_threads()
            try:
                fds = proc.num_fds()
            except:
                fds = -1
                
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"{timestamp}, {mem_info.rss / 1024 / 1024:.2f}, {threads}, {fds}")
            sys.stdout.flush()
            time.sleep(60)
            
    except psutil.NoSuchProcess:
        print(f"❌ Process {pid} not found")
    except KeyboardInterrupt:
        print("🛑 Monitoring stopped")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 monitor_runtime.py <PID>")
        sys.exit(1)
    
    monitor(int(sys.argv[1]))
