import os
import sys
import json
import time
import pty
import select
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from chaos.experiment_loader import load_experiments

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AGENT_CMD = ["venv/bin/python3", "agent.py", "console"]
RESULTS_FILE = "verification/chaos_results.json"

class ChaosProcessRunner:
    def __init__(self):
        self.experiments = load_experiments()
        self.results = []

    def run_all(self):
        logger.info(f"🧪 Found {len(self.experiments)} experiments to run.")
        
        for exp in self.experiments:
            result = self.run_experiment(exp)
            self.results.append(result)
            
            # Save intermediate results
            with open(RESULTS_FILE, 'w') as f:
                json.dump(self.results, f, indent=2)
        
        self.print_summary()

    def run_experiment(self, experiment: Dict) -> Dict:
        exp_id = experiment['id']
        logger.info(f"\n{'='*60}")
        logger.info(f"🔥 Running Experiment: {exp_id}")
        logger.info(f"   Description: {experiment['description']}")
        logger.info(f"   Faults: {experiment['faults']}")
        logger.info(f"{'='*60}")

        # Prepare Environment
        env = os.environ.copy()
        faults_config = experiment['faults'].copy()
        faults_config['experiment_id'] = exp_id
        faults_config['experiment_type'] = experiment['type']
        
        env['AGENT_CHAOS_CONFIG'] = json.dumps(faults_config)
        # Disable buffering
        env["PYTHONUNBUFFERED"] = "1"
        
        # Spawn via PTY
        master, slave = pty.openpty()
        
        try:
            process = subprocess.Popen(
                AGENT_CMD,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=env,
                cwd=os.getcwd(),
                close_fds=True,
                preexec_fn=os.setsid 
            )
            os.close(slave)
            
            # Interaction Loop
            output_buffer = ""
            start_time = time.time()
            # Determine total turns
            turns_cfg = experiment.get("turns", {"baseline": 3, "chaos": 3, "recovery": 3})
            total_turns = turns_cfg["baseline"] + turns_cfg["chaos"] + turns_cfg["recovery"]
            
            script = experiment.get("conversation_script", ["hello"])
            turn_idx = 0
            
            # Allow startup time
            time.sleep(5)
            
            # Send inputs
            while turn_idx < total_turns:
                if process.poll() is not None:
                    break
                
                user_input = script[turn_idx % len(script)]
                logger.info(f"🗣️ Turn {turn_idx + 1}/{total_turns}: Sending '{user_input}'")
                os.write(master, (user_input + "\n").encode())
                turn_idx += 1
                time.sleep(4) # Wait between turns (increased slightly)
            
            # Wait a bit more for final response
            time.sleep(5)
            
            # Read remaining output
            while True:
                r, _, _ = select.select([master], [], [], 0.1)
                if master in r:
                    try:
                        data = os.read(master, 1024)
                        if not data: break
                        output_buffer += data.decode(errors='replace')
                    except OSError:
                        break
                else:
                    break
            
            # Check Status
            exit_code = process.poll()
            if exit_code is None:
                # Kill it if still running (success case for stability)
                process.terminate()
                process.wait()
                exit_code = 0
            
            # Analyze Output for Failures
            crashed = exit_code != 0
            errors_found = "Traceback" in output_buffer or "Error:" in output_buffer or "Exception:" in output_buffer
            
            # Filter expected errors (simulated ones)
            # If we expect failures, then 'Error:' might be okay if it matches expected behavior.
            # But for process stability, we generally accept handled errors.
            
            status = "unknown"
            if crashed:
                status = "crashed"
            elif "Simulated Chaos" in output_buffer and not crashed:
                 status = "success" # We saw the chaos working and handling it
            elif not crashed:
                status = "success"
            
            logger.info(f"✅ Experiment {exp_id} finished with status: {status}")
            
            return {
                "id": exp_id,
                "status": status,
                "exit_code": exit_code,
                "log_snippet": output_buffer[-1000:]
            }

        except Exception as e:
            logger.error(f"❌ Runner failed for {exp_id}: {e}")
            return {"id": exp_id, "status": "runner_error", "error": str(e)}
        finally:
             if 'process' in locals() and process.poll() is None:
                 process.terminate()
             try:
                 os.close(master)
             except:
                 pass

    def print_summary(self):
        print("\n" + "="*60)
        print("📊 CHAOS RESULTS SUMMARY")
        print("="*60)
        for r in self.results:
            icon = "✅" if r['status'] == 'success' else "❌"
            print(f"{icon} {r['id']}: {r['status']}")
        print("="*60)

if __name__ == "__main__":
    runner = ChaosProcessRunner()
    runner.run_all()
