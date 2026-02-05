"""
Simulation Runner for Calamum Architecture (Agent + Librarian).
Validates the Feedback Loop between Producer and Consumer.
"""

import os
import sys
import time
import json
import shutil
import threading
import tempfile
from pathlib import Path
from concurrent import futures

# Add src to path
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

from calamum_observer_agent import AgentConfig, run_agent, append_record
from calamum_librarian import Librarian

def run_simulation():
    print("[Sim] Starting Calamum Architecture Simulation...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        data_dir = root / 'data'
        control_dir = root / 'control'
        health_dir = root / 'health'
        
        # Setup Env
        os.environ['CALAMUM_DATA_DIR'] = str(data_dir)
        os.environ['CALAMUM_CONTROL_DIR'] = str(control_dir)
        os.environ['CALAMUM_HEALTH_DIR'] = str(health_dir)
        
        # Ensure Dirs
        data_dir.mkdir()
        control_dir.mkdir()
        health_dir.mkdir()

        # 1. Seed strict policy (Low Limit)
        # 2KB limit to force rapid rotation
        initial_policy = {
            "max_bytes": 2048,
            "reason": "Simulation Seed"
        }
        (control_dir / 'rotation_policy.json').write_text(json.dumps(initial_policy))
        print(f"[Sim] Seeded Policy: Max Bytes = 2048")

        # 2. Configure Agent
        # Mocking the Agent Loop slightly to be faster for sim
        # We will use the actual 'run_agent' but we need to ensure it runs logic fast.
        # run_agent runs 'while True'. We can use a shared stop signal.
        
        # We'll just define a custom loop using the 'append_record' function directly
        # to have fine-grained control without modifying Agent source heavily.
        
        def agent_thread_func(stop_event):
            print("[Agent] Started.")
            jsonl_path = data_dir / "moltbook_stream.jsonl"
            node_id = "sim-node-01"
            
            iterations = 0
            while not stop_event.is_set():
                # Write record
                append_record(jsonl_path, node_id, "active", control_dir, data_dir)
                iterations += 1
                if iterations % 50 == 0:
                    time.sleep(0.1) 
            print("[Agent] Stopped.")

        # 3. Configure Librarian
        def librarian_thread_func(stop_event):
            print("[Librarian] Started.")
            lib = Librarian(interval_sec=0.5) # Fast scan
            # Override paths if Librarian init didn't pick up env vars (it should have)
            # Actually Librarian init calls get_calamum_* which read env vars.
            # But we set env vars inside this process, so it should work.

            while not stop_event.is_set():
                try:
                    lib.run_once()
                    lib._touch_heartbeat("ok")
                except Exception as e:
                    print(f"[Librarian] Error: {e}")
                time.sleep(0.5)
            print("[Librarian] Stopped.")

        # 4. Execution
        stop_event = threading.Event()
        
        with futures.ThreadPoolExecutor(max_workers=3) as executor:
            agent_future = executor.submit(agent_thread_func, stop_event)
            lib_future = executor.submit(librarian_thread_func, stop_event)

            # Monitor Phase
            print("[Sim] Monitoring for 5 seconds...")
            for i in range(10):
                time.sleep(0.5)
                
                # Check Policy
                try:
                    policy = json.loads((control_dir / 'rotation_policy.json').read_text())
                    limit = policy.get('max_bytes')
                    reason = policy.get('reason', '')
                    
                    # Count archives
                    archives = list((data_dir / 'archive').glob('*.jsonl.gz'))
                    
                    # Count raw logs (should be 0 or small if consumed)
                    pending = list((data_dir / 'archive').glob('*.jsonl'))
                    
                    print(f"[T+{i*0.5}s] Policy Limit: {limit} ({reason[:20]}...) | archives: {len(archives)} | pending: {len(pending)}")
                    
                    if limit > 2048 and "Adaptive" in reason:
                        print("SUCCESS: Feedback loop active! Policy increased.")
                        # We can stop early if success
                        # stop_event.set()
                        # break
                except Exception:
                    pass

            stop_event.set()
            print("[Sim] Stopping threads...")

    print("[Sim] Complete.")

if __name__ == "__main__":
    run_simulation()
