# Secure Launcher (PowerShell)
# Platform: Windows Host -> Docker (Linux Container)

$ErrorActionPreference = "Stop"

$IMAGE_NAME = "calamum-observer:stage2"
$CONTAINER_NAME = "calamum_observer_instance"

# Directory Setup
$SCRIPT_DIR = $PSScriptRoot
$REPO_ROOT = Resolve-Path "$SCRIPT_DIR\..\..\..\.."
$LOGS_DIR = Join-Path $REPO_ROOT "logs\data\calamum"

if (-not (Test-Path $LOGS_DIR)) {
    New-Item -ItemType Directory -Path $LOGS_DIR | Out-Null
}

Write-Host "[*] Building container image: $IMAGE_NAME"
docker build -t $IMAGE_NAME -f "$SCRIPT_DIR\Dockerfile" "$SCRIPT_DIR\.."

# Cleanup previous instance if exists
if (docker ps -a -q -f name=$CONTAINER_NAME) {
    Write-Host "[*] Removing previous instance..."
    docker rm -f $CONTAINER_NAME | Out-Null
}

Write-Host "[*] Launching Secure Observer (Glass Box Mode)..."
# Mapped to Windows paths
# Note: In WSL2 Docker, volume mounts work with Windows paths naturally

docker run -d --rm `
    --read-only `
    --cap-drop ALL `
    --security-opt "no-new-privileges:true" `
    --user 10001:10001 `
    --name $CONTAINER_NAME `
    -v "${LOGS_DIR}:/logs" `
    $IMAGE_NAME `
    python calamum_sampler.py --mode canary --output /logs/moltbook_canary_metrics.jsonl

Write-Host "[+] Observer running. ID: $CONTAINER_NAME"
Write-Host "[+] Triple-Redundancy Sentinel recommended: python projects/calamum-moltbook-observer/src/sentinel.py"
