# Run-CalamumWatchdog-Foreground.ps1
#
# Runs the Calamum watchdog in the foreground (no Start-Process) so a Scheduled Task
# can supervise the lifetime of the process (restart-on-failure semantics).
#
# Names-only discipline:
# - Do not print secrets.
# - Do not echo env var values.

[CmdletBinding()]
param(
    [switch]$NoRedirect
)

function Resolve-CidsRepoRoot {
    $explicit = $env:CODESENTINEL_REPO_ROOT
    if ($explicit) {
        try { return (Resolve-Path $explicit).Path } catch { }
    }

    $cursor = (Get-Location).Path
    while ($cursor -and (Test-Path $cursor)) {
        $marker = Join-Path $cursor 'codesentinel.json'
        if (Test-Path $marker) {
            return (Resolve-Path $cursor).Path
        }
        $parent = Split-Path -Parent $cursor
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }

    throw 'Unable to resolve CodeSentinel repo root. Set CODESENTINEL_REPO_ROOT or run from within the repository.'
}

$RepoRoot = Resolve-CidsRepoRoot
$CalamumRoot = Join-Path $RepoRoot 'projects\calamum-moltbook-observer'
$VenvPython = Join-Path $RepoRoot '.venv-core\Scripts\python.exe'
$WatchdogScript = Join-Path $CalamumRoot 'src\calamum_watchdog.py'
$LogDir = Join-Path $CalamumRoot 'logs'

if (-not (Test-Path $VenvPython)) {
    throw "Python executable not found: $VenvPython"
}
if (-not (Test-Path $WatchdogScript)) {
    throw "Watchdog script not found: $WatchdogScript"
}

# Ensure logs exist.
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Ensure child process can locate project root deterministically.
$env:CALAMUM_REPO_ROOT = $CalamumRoot
$env:CALAMUM_LOG_DIR = $LogDir
$env:PYTHONUNBUFFERED = '1'

if ($NoRedirect) {
    & $VenvPython -u $WatchdogScript
    exit $LASTEXITCODE
}

$stdout = Join-Path $LogDir 'calamum_watchdog.stdout.log'
$stderr = Join-Path $LogDir 'calamum_watchdog.stderr.log'

# Foreground run so Task Scheduler can restart on failure.
& $VenvPython -u $WatchdogScript 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
