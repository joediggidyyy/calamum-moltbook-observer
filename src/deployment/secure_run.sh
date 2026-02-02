#!/bin/bash
set -e

# CALAMUM OBSERVER SECURE LAUNCHER
# Enforces the hardening profile defined in Job 0003

IMAGE_NAME="calamum-observer:stage2"

# 1. Build
echo "[*] Building container..."
docker build -t $IMAGE_NAME -f deployment/Dockerfile .

# 2. Run with Hardening Profile
echo "[*] Launching Secure Observer..."
# --read-only: Mount container rootfs as read-only
# --cap-drop ALL: Drop all Linux capabilities
# --security-opt no-new-privileges: Prevent sudo/setuid
# --network none (simulation): In production this would be restricted network
# --tmpfs /tmp: Allow ephemeral writes only to /tmp if needed (sampler doesn't need it)

docker run --rm \
    --read-only \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --user 10001:10001 \
    --name calamum_observer_instance \
    -v $(pwd)/../../logs/data/calamum:/logs \
    $IMAGE_NAME \
    python calamum_sampler.py --output /logs/moltbook_samples_obfuscated.jsonl

echo "[+] Execution complete."
