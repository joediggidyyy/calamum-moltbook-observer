<#
KEYSMITH sandbox runner (names-only)

- Builds a minimal container image for KEYSMITH
- Runs KEYSMITH inside the container
- Persists artifacts to projects/calamum-moltbook-observer/local_untracked/ (gitignored)

Security rules:
- Never prints secrets
- Never opens sealed-drop file
- Only prints paths and presence

Prereq: Docker Desktop installed + running
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$BaseUrl = $(if ($env:MOLTBOOK_HOST) { $env:MOLTBOOK_HOST } else { "https://api.moltbook.com/v1" }),
    [string]$RegisterPath = $(if ($env:MOLTBOOK_KEYSMITH_REGISTER_PATH) { $env:MOLTBOOK_KEYSMITH_REGISTER_PATH } else { "agents/register" }),
    [string[]]$AllowHost = @("api.moltbook.com", "moltbook.com"),
    [string]$AgentMetadataJson = "",
    [string]$OutputDir = ""
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.."))
$localUntracked = Join-Path $projectRoot "local_untracked"

$ts = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $localUntracked (Join-Path "keysmith_exports" $ts)
}

# Ensure host output directory exists (gitignored by project policy).
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$imageName = "calamum-keysmith:local"
$dockerfile = Join-Path $projectRoot "deployment\keysmith\Dockerfile"

Write-Output "[INFO] Building KEYSMITH sandbox image (names-only)"
Write-Output "project_root=$($projectRoot.Path)"
Write-Output "output_dir=$OutputDir"

# Build image using the Calamum project folder as the build context.
& docker build -f $dockerfile -t $imageName $projectRoot.Path
if ($LASTEXITCODE -ne 0) {
    throw "Docker build failed"
}

# Map local_untracked into container so artifacts persist on host.
$volumeArg = "${localUntracked}:/app/local_untracked"

$containerOutputDir = $OutputDir.Replace($localUntracked, "/app/local_untracked").Replace("\\", "/")

$args = @(
    "run", "--rm",
    "-e", "KEYSMITH_SANDBOX=1",
    "-v", $volumeArg,
    $imageName,
    "mint",
    "--base-url", $BaseUrl,
    "--register-path", $RegisterPath,
    "--output-dir", $containerOutputDir
)

foreach ($h in $AllowHost) {
    if (-not [string]::IsNullOrWhiteSpace($h)) {
        $args += @("--allow-host", $h)
    }
}

if ($DryRun) {
    $args += "--dry-run"
}

if (-not [string]::IsNullOrWhiteSpace($AgentMetadataJson)) {
    # If provided, caller must ensure this path is accessible inside the container.
    $args += @("--agent-metadata-json", $AgentMetadataJson)
}

Write-Output "[INFO] Running KEYSMITH in sandbox (names-only)"
& docker @args
if ($LASTEXITCODE -ne 0) {
    throw "KEYSMITH sandbox run failed"
}

Write-Output "[OK] KEYSMITH completed (names-only)"
Write-Output "output_dir=$OutputDir"
Write-Output "claim_url_path=$(Join-Path $OutputDir 'claim_url.txt')"
Write-Output "sealed_drop_path=$(Join-Path $OutputDir 'sealed_drop.bin')"
Write-Output "import_helper_path=$(Join-Path $OutputDir 'Import-MoltbookApiKeyFromSealedDrop.ps1')"
Write-Output "audit_path=$(Join-Path $OutputDir 'keysmith_audit.jsonl')"
