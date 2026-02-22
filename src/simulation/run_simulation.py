"""
Simulation Runner for Calamum Architecture (Agent + Librarian).
Validates the Feedback Loop between Producer and Consumer.
"""

import os
import sys
import time
import json
import threading
import tempfile
from pathlib import Path
from concurrent import futures

# Add src to path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.append(str(src_dir))

from calamum_observer_agent import append_record
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
        print("[Sim] Seeded Policy: Max Bytes = 2048")

        def agent_thread_func(stop_event):
            print("[Agent] Started.")
            jsonl_path = data_dir / "moltbook_stream.jsonl"
            node_id = "sim-node-01"

            iterations = 0
            while not stop_event.is_set():
                append_record(jsonl_path, node_id, "active", control_dir, data_dir)
                iterations += 1
                if iterations % 50 == 0:
                    time.sleep(0.1)
            print("[Agent] Stopped.")

        def librarian_thread_func(stop_event):
            print("[Librarian] Started.")
            lib = Librarian(interval_sec=0.5)

            while not stop_event.is_set():
                try:
                    lib.run_once()
                    lib._touch_heartbeat("ok")
                except Exception as e:
                    print(f"[Librarian] Error: {e}")
                time.sleep(0.5)
            print("[Librarian] Stopped.")

        stop_event = threading.Event()

        with futures.ThreadPoolExecutor(max_workers=3) as executor:
            _agent_future = executor.submit(agent_thread_func, stop_event)
            _lib_future = executor.submit(librarian_thread_func, stop_event)

            print("[Sim] Monitoring for 5 seconds...")
            for i in range(10):
                time.sleep(0.5)

                try:
                    policy = json.loads((control_dir / 'rotation_policy.json').read_text())
                    limit = policy.get('max_bytes')
                    reason = policy.get('reason', '')

                    archives = list((data_dir / 'archive').glob('*.jsonl.gz'))
                    pending = list((data_dir / 'archive').glob('*.jsonl'))

                    print(f"[T+{i*0.5}s] Policy Limit: {limit} ({reason[:20]}...) | archives: {len(archives)} | pending: {len(pending)}")

                    if limit > 2048 and "Adaptive" in reason:
                        print("SUCCESS: Feedback loop active! Policy increased.")
                except Exception:
                    pass

            stop_event.set()
            print("[Sim] Stopping threads...")

    print("[Sim] Complete.")


if __name__ == "__main__":
    run_simulation()
