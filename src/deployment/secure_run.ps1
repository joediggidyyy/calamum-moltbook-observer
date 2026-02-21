<#
Secure Launcher (PowerShell)
Platform: Windows Host -> Docker (Linux Container)

This script is part of Stage 2 (Container Hardening) and is intended to be
publish-grade reproducible.

Names-only discipline:
- Do not print secret values.
- If live is requested, fail closed when MOLTBOOK_API_KEY is absent.

Modes:
- Mode = sampler|canary controls schema/stream type.
- Source = sim|live controls where items come from.
#>

[CmdletBinding()]
param(
    [ValidateSet('sampler', 'canary')]
    [string]$Mode = 'canary',

    [ValidateSet('sim', 'live')]
    [string]$Source = 'sim',

    [string]$ImageName = 'calamum-observer:stage2',

    [string]$ContainerName = 'calamum_observer_instance'
)

$ErrorActionPreference = "Stop"

function Invoke-DockerStrict {
    param(
        [string[]]$Args,
        [string]$Step
    )

    & docker @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker step failed: $Step (exit=$LASTEXITCODE)"
    }
}

function Test-EnvPresent($name) {
    try {
        return (Test-Path "env:$name") -and -not [string]::IsNullOrWhiteSpace((Get-Item "env:$name").Value)
    } catch { }
    return $false
}

# Directory Setup
$SCRIPT_DIR = $PSScriptRoot

# Calamum operational root is the project root.
$PROJECT_ROOT = Resolve-Path "$SCRIPT_DIR\..\.."
$LOGS_DIR = Join-Path $PROJECT_ROOT "logs\data\calamum"

if (-not (Test-Path $LOGS_DIR)) {
    New-Item -ItemType Directory -Path $LOGS_DIR | Out-Null
}

if ($Source -eq 'live') {
    if (-not (Test-EnvPresent 'MOLTBOOK_API_KEY')) {
        Write-Host "[!] LIVE requested (Source=live) but MOLTBOOK_API_KEY is missing. Refusing to start container." -ForegroundColor Red
        exit 2
    }
}

# Fail closed if Docker daemon is not reachable.
Invoke-DockerStrict -Args @('info') -Step 'docker daemon availability check'

$outputName = if ($Mode -eq 'canary') { 'moltbook_canary_metrics.jsonl' } else { 'moltbook_samples_obfuscated.jsonl' }
$containerOut = "/logs/$outputName"

Write-Host "[*] Building container image: $ImageName"
Invoke-DockerStrict -Args @('build', '-t', $ImageName, '-f', "$SCRIPT_DIR\Dockerfile", "$SCRIPT_DIR\..") -Step 'docker build'

# Cleanup previous instance if exists
$existingContainer = & docker ps -a -q -f "name=$ContainerName"
if ($LASTEXITCODE -ne 0) {
    throw "Docker step failed: docker ps existing container check (exit=$LASTEXITCODE)"
}

if ($existingContainer) {
    Write-Host "[*] Removing previous instance..."
    Invoke-DockerStrict -Args @('rm', '-f', $ContainerName) -Step 'docker rm'
}

Write-Host "[*] Launching Secure Observer (Glass Box Mode)..."
Write-Host "[*] Config (names-only): mode=$Mode source=$Source output=$outputName" -ForegroundColor Gray
# Mapped to Windows paths
# Note: In WSL2 Docker, volume mounts work with Windows paths naturally

$envArgs = @()
if ($Source -eq 'live') {
    # Pass through by name only; Docker will take values from the host environment.
    $envArgs += @('-e', 'MOLTBOOK_API_KEY')
    if (Test-EnvPresent 'MOLTBOOK_HOST') {
        $envArgs += @('-e', 'MOLTBOOK_HOST')
    }
}

& docker run -d --rm `
    --read-only `
    --cap-drop ALL `
    --security-opt "no-new-privileges:true" `
    --user 10001:10001 `
    --name $ContainerName `
    -v "${LOGS_DIR}:/logs" `
    @envArgs `
    $ImageName `
    python calamum_sampler.py --mode $Mode --source $Source --output $containerOut

if ($LASTEXITCODE -ne 0) {
    throw "Docker step failed: docker run (exit=$LASTEXITCODE)"
}

Write-Host "[+] Observer running. ID: $ContainerName"
Write-Host "[+] Triple-Redundancy Sentinel recommended: python projects/calamum-moltbook-observer/src/sentinel.py"
