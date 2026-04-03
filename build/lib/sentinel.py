import time
import subprocess
import sys
import logging
from pathlib import Path
from datetime import datetime

# CONFIGURATION
CONTAINER_NAME = "calamum_observer_instance"
CHECK_INTERVAL_SEC = 5
MAX_SILENCE_SEC = 300  # Kill if no logs for 5 mins
FORBIDDEN_KEYWORDS = [
    "Traceback", 
    "Error", 
    "Exception", 
    "leaking", 
    "Permission denied", # Should not happen if app is behaving
]

# Set up logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SENTINEL] %(levelname)s: %(message)s'
)

def run_cmd(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

def kill_infrastructure(reason: str):
    logging.critical(f"INITIATING EMERGENCY SHUTDOWN. Reason: {reason}")
    # 1. Kill Container
    run_cmd(f"docker kill {CONTAINER_NAME}")
    logging.info(f"Container {CONTAINER_NAME} killed.")
    
    # 2. (Optional) Network isolation or alerting
    # run_cmd("disconnect_network...")
    
    logging.critical("INFRASTRUCTURE SECURED. INVESTIGATION REQUIRED.")
    sys.exit(1)

def check_container_health():
    # 1. Liveness
    res = run_cmd(f"docker ps -q -f name={CONTAINER_NAME}")
    if not res.stdout.strip():
        logging.warning("Target container not found (may have exited normally or crashed).")
        return False

    # 2. Log Analysis (Last 20 lines)
    res = run_cmd(f"docker logs --tail 20 {CONTAINER_NAME}")
    logs = res.stdout + res.stderr
    
    for kw in FORBIDDEN_KEYWORDS:
        if kw in logs:
            kill_infrastructure(f"Forbidden keyword detected in logs: '{kw}'")

    return True

def main():
    logging.info(f"Sentinel active. Watching: {CONTAINER_NAME}")
    
    last_activity = time.time()
    
    try:
        while True:
            alive = check_container_health()
            if not alive:
                # If intended to run forever, this is a crash.
                # If batch job, it's normal.
                logging.info("Container stopped. Sentinel exiting.")
                break
                
            # Heartbeat check could go here if we tail the output file
            # ...
            
            time.sleep(CHECK_INTERVAL_SEC)
            
    except KeyboardInterrupt:
        logging.info("Sentinel stopped by user.")

if __name__ == "__main__":
    main()
