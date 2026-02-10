# Register-CalamumWatchdogStartupTask.ps1
#
# Registers (or updates) a Windows Scheduled Task that starts the Calamum watchdog
# at OS startup (no interactive login required).
#
# Operational intent:
# - The watchdog owns daily reporting/audit schedules.
# - If the system is running, we get reports; if it is not, we do not.
# - Startup catch-up is handled inside the watchdog.
#
# Names-only discipline:
# - This script never prints env var values.
# - No secrets are embedded in the task.

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'Calamum_Watchdog_AtStartup',
    [switch]$RunAsSystem
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
$RunnerPath = Join-Path $RepoRoot 'projects\calamum-moltbook-observer\tools\windows\Run-CalamumWatchdog-Foreground.ps1'

if (-not (Test-Path $RunnerPath)) {
    throw "Runner script not found at: $RunnerPath"
}

# Run PowerShell non-interactively.
$actionArgs = @(
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    ('"' + $RunnerPath + '"')
) -join ' '

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $actionArgs -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtStartup

# Principal selection:
# - Recommended: SYSTEM (no password storage, runs without login)
# - Optional: current user (InteractiveToken) for dev-only; note this does NOT satisfy "no login".
if ($RunAsSystem) {
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType InteractiveToken -RunLevel Highest
}

# Keep task running as long as the watchdog runs, and restart if it fails.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)

$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings

$runAsLabel = if ($RunAsSystem) { 'SYSTEM' } else { $env:USERNAME }

$didRegister = $false
$wasWhatIf = $false

if ($PSCmdlet.ShouldProcess("ScheduledTask:$TaskName", 'Register/Update')) {
    try {
        Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force -ErrorAction Stop | Out-Null
        $didRegister = $true
    } catch {
        Write-Error "[ERROR] Failed to register scheduled task '$TaskName': $($_.Exception.Message)"
        exit 1
    }
} else {
    # When -WhatIf is used, ShouldProcess emits the WhatIf message and returns false.
    $wasWhatIf = $true
}

$statusLabel = if ($didRegister) { '[OK]' } else { '[WHATIF]' }
$color = if ($didRegister) { 'Green' } else { 'Yellow' }

Write-Host "$statusLabel Scheduled task registered/updated: $TaskName" -ForegroundColor $color
Write-Host "     Trigger: AtStartup" -ForegroundColor Gray
Write-Host "     RunAs: $runAsLabel" -ForegroundColor Gray
Write-Host "     Runner: projects/calamum-moltbook-observer/tools/windows/Run-CalamumWatchdog-Foreground.ps1" -ForegroundColor Gray
Write-Host "     Note: Use -RunAsSystem to satisfy 'no user login required'." -ForegroundColor Gray

if ($wasWhatIf) {
    Write-Host "     Note: This was a dry-run (-WhatIf)." -ForegroundColor Gray
}
