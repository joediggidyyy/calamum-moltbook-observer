# TAG: GHOST_CONSOLE_LAUNCHER
# Launcher for Calamum Ops Widget (Ghost Console) + Observer Stack
# Stack Protocol: Agent -> Librarian -> Dashboard -> Frontend

# --- CONFIGURATION ---
$CalamumRoot = Resolve-Path "$PSScriptRoot" 
$WorkspaceRoot = Resolve-Path "$PSScriptRoot\..\.." 
$VenvPython = Join-Path $WorkspaceRoot ".venv-core\Scripts\python.exe"
$SrcDir = Join-Path $PSScriptRoot "src"
$LogDir = Join-Path $CalamumRoot "logs"

# Artifacts
$DashboardScript = Join-Path $SrcDir "ops_dashboard.py"
$AgentScript = Join-Path $SrcDir "calamum_observer_agent.py"
$LibrarianScript = Join-Path $SrcDir "calamum_librarian.py"
$WatchdogScript = Join-Path $SrcDir "calamum_watchdog.py"

# PID Tracking
$DashboardPidFile = Join-Path $PSScriptRoot "ghost_console.pid"
$AgentPidFile = Join-Path $PSScriptRoot "calamum_agent.pid"
$LibrarianPidFile = Join-Path $PSScriptRoot "calamum_librarian.pid"
$WatchdogPidFile = Join-Path $PSScriptRoot "calamum_watchdog.pid"

# Dashboard Config
$Port = 8899
$Url = "http://localhost:$Port"

# --- HELPER FUNCTIONS ---

function Stop-ByPidFile ($pidFile, $name) {
    if (Test-Path $pidFile) {
        try {
            $pidVal = Get-Content $pidFile -ErrorAction Stop
            if ($pidVal -and $pidVal -match '^\d+$') {
                $id = [int]$pidVal
                $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
                if ($proc) {
                    Write-Host "    -> Stopping $name (PID: $id)..." -ForegroundColor Yellow
                    function Get-ProcessTreePids($rootPid) {
                        $all = @()
                        $seen = @{}
                        $queue = New-Object System.Collections.Generic.Queue[int]
                        $queue.Enqueue([int]$rootPid)
                        while ($queue.Count -gt 0) {
                            $cur = $queue.Dequeue()
                            if ($seen.ContainsKey($cur)) { continue }
                            $seen[$cur] = $true
                            $all += $cur
                            try {
                                $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$cur" -ErrorAction SilentlyContinue
                                foreach ($k in $kids) {
                                    if ($k.ProcessId) {
                                        $queue.Enqueue([int]$k.ProcessId)
                                    }
                                }
                            } catch { }
                        }
                        return ($all | Select-Object -Unique)
                    }

                    function Wait-PidsExit($pidList, $timeoutMs) {
                        $deadline = (Get-Date).AddMilliseconds([int]$timeoutMs)
                        while ((Get-Date) -lt $deadline) {
                            $alive = @()
                            foreach ($pidItem in $pidList) {
                                if (Get-Process -Id ([int]$pidItem) -ErrorAction SilentlyContinue) {
                                    $alive += [int]$pidItem
                                }
                            }
                            if ($alive.Count -eq 0) {
                                return $true
                            }
                            Start-Sleep -Milliseconds 100
                        }
                        return $false
                    }

                    $tree = Get-ProcessTreePids $id
                    # Graceful first: request stop without force, children first.
                    foreach ($pidItem in ($tree | Sort-Object -Descending)) {
                        try {
                            Stop-Process -Id ([int]$pidItem) -ErrorAction SilentlyContinue
                        } catch { }
                    }

                    $exited = Wait-PidsExit $tree 3000
                    if (-not $exited) {
                        Write-Host "    [!] $name did not exit cleanly in grace window. Escalating..." -ForegroundColor Yellow
                        foreach ($pidItem in ($tree | Sort-Object -Descending)) {
                            try {
                                Stop-Process -Id ([int]$pidItem) -Force -ErrorAction SilentlyContinue
                            } catch { }
                        }
                        [void](Wait-PidsExit $tree 1500)
                    }
                }
            }
        } catch { }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Start-ServiceScript ($name, $scriptPath, $pidFile, $argsList=@()) {
    Write-Host "[*] Starting $name..." -ForegroundColor Cyan
    $logOut = Join-Path $LogDir "${name}.stdout.log"
    $logErr = Join-Path $LogDir "${name}.stderr.log"
    
    # Ensure logs exist
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    
    # On Windows, venv python.exe can act as a launcher that spawns the real interpreter.
    # We prefer to track the child (real) PID in pidfiles, and treat the parent launcher
    # as part of the same service instance.
    function Resolve-RealPythonChildPid ($parentPid, $scriptPath) {
        try {
            if (-not $parentPid) { return $null }
            $needle = [System.IO.Path]::GetFileName($scriptPath)
            $deadline = (Get-Date).AddSeconds(2)
            while ((Get-Date) -lt $deadline) {
                try {
                    $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$parentPid" -ErrorAction SilentlyContinue
                    foreach ($k in ($kids | Where-Object { $_.CommandLine -and ($_.CommandLine -like "*${needle}*") })) {
                        if ($k.ProcessId) { return [int]$k.ProcessId }
                    }
                } catch { }
                Start-Sleep -Milliseconds 100
            }
        } catch { }
        return $null
    }

    try {
        $proc = Start-Process -FilePath $VenvPython `
            -ArgumentList (@("-u", $scriptPath) + $argsList) `
            -WindowStyle Hidden `
            -PassThru `
            -RedirectStandardOutput $logOut `
            -RedirectStandardError $logErr

        if ($proc -and $proc.Id) {
            $realPid = Resolve-RealPythonChildPid $proc.Id $scriptPath
            if (-not $realPid) { $realPid = [int]$proc.Id }
            Set-Content -Path $pidFile -Value $realPid -Encoding ASCII
            if ($realPid -ne [int]$proc.Id) {
                Write-Host "    -> Started (PID: $realPid) [launcher_pid: $($proc.Id)]" -ForegroundColor Green
            } else {
                Write-Host "    -> Started (PID: $realPid)" -ForegroundColor Green
            }
        } else {
            Write-Host "    [!] Failed to start $name" -ForegroundColor Red
        }
    } catch {
        # Some processes can hold an exclusive lock on the log files (common on Windows).
        # If we cannot open the stable log file, fall back to a timestamped alternate.
        $msg = "$_"
        if ($msg -like "*cannot access the file*being used by another process*") {
            $ts = (Get-Date).ToString('yyyyMMdd_HHmmss_fff')
            $altOut = Join-Path $LogDir "${name}.stdout.${ts}.log"
            $altErr = Join-Path $LogDir "${name}.stderr.${ts}.log"
            Write-Host "    [!] Log file lock detected for ${name}. Using alternate logs:" -ForegroundColor Yellow
            Write-Host "        stdout -> $altOut" -ForegroundColor Yellow
            Write-Host "        stderr -> $altErr" -ForegroundColor Yellow

            try {
                $proc = Start-Process -FilePath $VenvPython `
                    -ArgumentList (@("-u", $scriptPath) + $argsList) `
                    -WindowStyle Hidden `
                    -PassThru `
                    -RedirectStandardOutput $altOut `
                    -RedirectStandardError $altErr

                if ($proc -and $proc.Id) {
                    $realPid = Resolve-RealPythonChildPid $proc.Id $scriptPath
                    if (-not $realPid) { $realPid = [int]$proc.Id }
                    Set-Content -Path $pidFile -Value $realPid -Encoding ASCII
                    if ($realPid -ne [int]$proc.Id) {
                        Write-Host "    -> Started (PID: $realPid) [launcher_pid: $($proc.Id)]" -ForegroundColor Green
                    } else {
                        Write-Host "    -> Started (PID: $realPid)" -ForegroundColor Green
                    }
                    return
                }
            } catch {
                Write-Host "    [!] Error starting ${name} (alt logs): $($_)" -ForegroundColor Red
                return
            }
        }

        Write-Host "    [!] Error starting ${name}: $($_)" -ForegroundColor Red
    }
}

# Return a list of PIDs whose command line indicates they are running a given script.
function Get-PidsByScript ($scriptPath) {
    $pids = @()
    try {
        $needle = [System.IO.Path]::GetFileName($scriptPath)
        $full = (Resolve-Path $scriptPath -ErrorAction SilentlyContinue)
        $fullStr = $null
        if ($full) {
            $fullStr = "$full"
        }
        $items = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            if (-not $_.CommandLine) { return $false }
            if ($fullStr -and ($_.CommandLine -like "*${fullStr}*")) { return $true }
            return ($_.CommandLine -like "*${needle}*")
        }
        foreach ($it in $items) {
            if ($it.ProcessId) {
                $pids += [int]$it.ProcessId
            }
        }
    } catch { }
    return ($pids | Select-Object -Unique)
}

# Enforce single-instance semantics: kill any extra instances beyond the expected PID.
function Stop-OrphanInstances ($name, $scriptPath, $expectedPid) {
    $pids = Get-PidsByScript $scriptPath
    $needle = [System.IO.Path]::GetFileName($scriptPath)

    # Protect the expected PID and its parent launcher PID (venv python.exe -> base python.exe).
    $protected = @{}
    if ($expectedPid) {
        $protected[[int]$expectedPid] = $true
        try {
            $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$expectedPid" -ErrorAction SilentlyContinue
            if ($ci -and $ci.ParentProcessId) {
                $parentId = [int]$ci.ParentProcessId
                # Always protect direct parent of expected PID.
                # On Windows, terminating the parent launcher can cascade and
                # tear down the still-valid expected child process.
                $protected[$parentId] = $true
            }
        } catch { }
    }

    foreach ($procId in $pids) {
        if ($protected.ContainsKey([int]$procId)) {
            continue
        }
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "    [!] Orphan instance detected for ${name} (PID: ${procId}). Stopping..." -ForegroundColor Yellow
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        } catch { }
    }
}

# --- EXECUTION ---

Write-Host "=== CALAMUM OPS STACK LAUNCHER ===" -ForegroundColor Green

# Normalize agent args so common operator inputs (CANARY, HONEYPOT, ACTIVE_GATED, etc.)
# map cleanly to what the Python agent expects.
function Normalize-AgentMode($raw) {
    if ($null -eq $raw) { return "canary" }
    $v = ("$raw").Trim()
    if (-not $v) { return "canary" }
    $lower = $v.ToLowerInvariant().Replace(' ', '_')

    if ($lower -eq "canary") { return "canary" }
    if ($lower -eq "active_gated" -or $lower -eq "activegated" -or $lower -eq "active-gated") { return "active-gated" }

    # Default: preserve intent but keep it shell-safe + consistent.
    return $lower.Replace('_', '-')
}

function Normalize-AgentSource($raw) {
    if ($null -eq $raw) { return "sim" }
    $v = ("$raw").Trim()
    if (-not $v) { return "sim" }
    $lower = $v.ToLowerInvariant()
    if ($lower -eq "live" -or $lower -eq "real") { return "real" }
    return "sim"
}

function Requires-MoltbookKey($source, $mode) {
    $src = ("$source").Trim().ToLowerInvariant()
    $m = ("$mode").Trim().ToLowerInvariant().Replace('_', '-')
    if ($src -ne 'real') { return $false }
    return ($m -in @('live', 'honeypot'))
}

function Resolve-AgentIntervalSec() {
    $defaultVal = "2.0"
    try {
        if (Test-Path env:CALAMUM_AGENT_INTERVAL_SEC) {
            $raw = (Get-Item env:CALAMUM_AGENT_INTERVAL_SEC).Value
            if (-not [string]::IsNullOrWhiteSpace($raw)) {
                $f = [double]::Parse($raw, [System.Globalization.CultureInfo]::InvariantCulture)
                if ($f -gt 0) {
                    return $raw
                }
            }
        }
    } catch { }
    return $defaultVal
}

function Resolve-ObserverAutostart() {
    # GUI-safe default: observer does NOT autostart unless explicitly enabled.
    $raw = $null
    try {
        if (Test-Path env:CALAMUM_GUI_AUTOSTART_OBSERVER) {
            $raw = (Get-Item env:CALAMUM_GUI_AUTOSTART_OBSERVER).Value
        }
    } catch { }

    if ($null -eq $raw) { return $false }
    $v = ("$raw").Trim().ToLowerInvariant()
    if (-not $v) { return $false }
    return ($v -in @('1', 'true', 'yes', 'on', 'enable', 'enabled'))
}

# Load a project-local .env (gitignored) if present.
# - Names-only discipline: do not print values.
# - Do not overwrite non-empty env vars already present in the session.
function Import-ProjectDotEnv($dotenvPath) {
    if (-not (Test-Path $dotenvPath)) { return }
    try {
        $lines = Get-Content -Path $dotenvPath -ErrorAction Stop
    } catch {
        return
    }

    foreach ($rawLine in $lines) {
        if ($null -eq $rawLine) { continue }
        $line = ("$rawLine").Trim()
        if (-not $line) { continue }
        if ($line.StartsWith('#')) { continue }

        $m = [regex]::Match($line, '^(?<k>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<v>.*)$')
        if (-not $m.Success) { continue }

        $k = $m.Groups['k'].Value
        $v = $m.Groups['v'].Value
        if ($null -eq $k -or -not $k) { continue }

        # Strip optional surrounding quotes.
        $v = $v.Trim()
        if ($v.StartsWith('"') -and $v.EndsWith('"') -and $v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }
        if ($v.StartsWith("'") -and $v.EndsWith("'") -and $v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }

        if ([string]::IsNullOrWhiteSpace($v)) { continue }

        $existing = $null
        try {
            if (Test-Path "env:$k") { $existing = (Get-Item "env:$k").Value }
        } catch { }

        if (-not [string]::IsNullOrWhiteSpace($existing)) {
            continue
        }

        try {
            Set-Item -Path "env:$k" -Value $v
        } catch { }
    }
}

$DotEnv = Join-Path $CalamumRoot '.env'
if (Test-Path $DotEnv) {
    Write-Host "[*] Found project .env (gitignored): $DotEnv" -ForegroundColor Gray
    Import-ProjectDotEnv $DotEnv
} else {
    Write-Host "[*] Project .env not found (OK if env is injected elsewhere)." -ForegroundColor Gray
}

# Names-only presence checks (do not print values)
$signingPresent = (Test-Path env:CALAMUM_DATA_SIGNING_KEY) -and -not [string]::IsNullOrWhiteSpace((Get-Item env:CALAMUM_DATA_SIGNING_KEY).Value)
$moltKeyPresent = (Test-Path env:MOLTBOOK_API_KEY) -and -not [string]::IsNullOrWhiteSpace((Get-Item env:MOLTBOOK_API_KEY).Value)
Write-Host ("[*] Env presence: CALAMUM_DATA_SIGNING_KEY=" + $(if ($signingPresent) { 'present' } else { 'MISSING' })) -ForegroundColor Gray
Write-Host ("[*] Env presence: MOLTBOOK_API_KEY=" + $(if ($moltKeyPresent) { 'present' } else { 'MISSING' })) -ForegroundColor Gray

# Determine desired agent configuration from env (or safe defaults)
$desiredMode = Normalize-AgentMode $(if (Test-Path env:CALAMUM_OPS_MODE) { (Get-Item env:CALAMUM_OPS_MODE).Value } else { $null })
$desiredSource = Normalize-AgentSource $(if (Test-Path env:CALAMUM_MOLTBOOK_SOURCE) { (Get-Item env:CALAMUM_MOLTBOOK_SOURCE).Value } else { $null })
$desiredInterval = Resolve-AgentIntervalSec
$autoStartObserver = Resolve-ObserverAutostart

Write-Host ("[*] Agent config (names-only): mode=${desiredMode}, source=${desiredSource}, interval_sec=${desiredInterval}") -ForegroundColor Gray
Write-Host ("[*] GUI observer autostart: " + $(if ($autoStartObserver) { 'ENABLED' } else { 'DISABLED (default)' })) -ForegroundColor Gray

# Fail closed only for real-source lockdown lanes that require live retrieval.
if ((Requires-MoltbookKey $desiredSource $desiredMode) -and -not $moltKeyPresent) {
    Write-Host "[!] REAL source requested in ${desiredMode} mode but MOLTBOOK_API_KEY is missing. Refusing to start observer agent." -ForegroundColor Red
    Write-Host "    -> Fix: inject env vars via VAULT tooling or populate project .env (gitignored), then re-run this launcher." -ForegroundColor Yellow
    exit 2
}

# Ensure child processes treat the Calamum project as the operational root.
$env:CALAMUM_REPO_ROOT = "$CalamumRoot"
$env:CALAMUM_LOG_DIR = "$LogDir"

# 1. CORE PROCESS CHECK (Daemon/Watchdog/Librarian)

# Helper to read a pidfile and return the PID if the process is running.
function Get-RunningPid($pidFile) {
    if (Test-Path $pidFile) {
        try {
            $idRaw = Get-Content $pidFile -ErrorAction Stop | Select-Object -First 1
            $id = ("$idRaw").Trim()
            if ($id -and $id -match '^\d+$') {
                $pidVal = [int]$id
                if (Get-Process -Id $pidVal -ErrorAction SilentlyContinue) {
                    return $pidVal
                }
            }
        } catch { }
    }
    return $null
}

# Helper to detect the process actually owning a LISTEN socket on a local port.
function Get-PortOwningPid($port) {
    try {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($listeners) {
            $owning = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
            if ($owning) {
                return ($owning | Select-Object -First 1)
            }
        }
    } catch { }
    return $null
}

Write-Host "[*] Checking Core Stack Integrity..." -ForegroundColor Cyan

# Check/Start Watchdog Supervisor
$watchdogPid = Get-RunningPid $WatchdogPidFile
Stop-OrphanInstances "Watchdog" $WatchdogScript $watchdogPid
if (-not $watchdogPid) {
    Write-Host "    [!] Watchdog Supervisor not running. Starting..." -ForegroundColor Yellow
    Start-ServiceScript "calamum_watchdog" $WatchdogScript $WatchdogPidFile
} else {
    Write-Host "    [+] Watchdog Supervisor is ACTIVE (PID: $watchdogPid)" -ForegroundColor Green
}

# Check/Start Agent
$agentPid = Get-RunningPid $AgentPidFile
Stop-OrphanInstances "Observer Agent" $AgentScript $agentPid
if (-not $autoStartObserver) {
    if ($agentPid) {
        Write-Host "    [+] Observer Agent is ACTIVE (PID: $agentPid) [autostart disabled; leaving as-is]" -ForegroundColor Green
    } else {
        Write-Host "    [*] Observer Agent autostart disabled for GUI launch (set CALAMUM_GUI_AUTOSTART_OBSERVER=1 to enable)." -ForegroundColor Gray
    }
} else {
    Stop-OrphanInstances "Observer Agent" $AgentScript $agentPid
    if (-not $agentPid) {
        Write-Host "    [!] Observer Agent not running. Starting..." -ForegroundColor Yellow
        Start-ServiceScript "calamum_agent" $AgentScript $AgentPidFile @(
            "--mode", $desiredMode,
            "--source", $desiredSource,
            "--interval-sec", $desiredInterval
        )
    } else {
        # If the agent is running but not in the desired config, restart it.
        $needsRestart = $false
        try {
            $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$agentPid" -ErrorAction SilentlyContinue
            $cmd = $null
            if ($ci) { $cmd = $ci.CommandLine }
            if ($cmd) {
                if ($cmd -notlike "*--mode*${desiredMode}*") { $needsRestart = $true }
                if ($cmd -notlike "*--source*${desiredSource}*") { $needsRestart = $true }
            } else {
                # If we can't see the command line, be conservative and restart.
                $needsRestart = $true
            }
        } catch {
            $needsRestart = $true
        }

        if ($needsRestart) {
            Write-Host "    [!] Observer Agent config mismatch or unknown. Restarting to apply env-driven settings..." -ForegroundColor Yellow
            Stop-ByPidFile $AgentPidFile "Observer Agent"
            Start-ServiceScript "calamum_agent" $AgentScript $AgentPidFile @(
                "--mode", $desiredMode,
                "--source", $desiredSource,
                "--interval-sec", $desiredInterval
            )
        } else {
            Write-Host "    [+] Observer Agent is ACTIVE (PID: $agentPid)" -ForegroundColor Green
        }
    }
}

# Check/Start Librarian
$librarianPid = Get-RunningPid $LibrarianPidFile
Stop-OrphanInstances "Librarian" $LibrarianScript $librarianPid
if (-not $librarianPid) {
    Write-Host "    [!] Librarian not running. Starting..." -ForegroundColor Yellow
    Start-ServiceScript "calamum_librarian" $LibrarianScript $LibrarianPidFile
} else {
    Write-Host "    [+] Librarian Daemon is ACTIVE (PID: $librarianPid)" -ForegroundColor Green
}

# Check/Start Dashboard (GUI Backend)
# The dashboard is technically the 'Convenience Layer' but currently provides the API for the UI.
# It should be treated as a service for the frontend.
$dashboardPid = Get-RunningPid $DashboardPidFile

# If we think the dashboard is running but it is not LISTENing on the expected port,
# treat it as unhealthy and restart it.
if ($dashboardPid) {
    $ownerNow = Get-PortOwningPid $Port
    if ($ownerNow) {
        if ($dashboardPid -ne $ownerNow) {
            Write-Host "    [!] Dashboard PID mismatch detected (pidfile=$dashboardPid, port_owner=$ownerNow). Keeping pidfile on script PID to avoid killing the parent process." -ForegroundColor Yellow
        }
    } else {
        Write-Host "    [!] Dashboard PID present but port $Port is not LISTENing. Restarting..." -ForegroundColor Yellow
        Stop-ByPidFile $DashboardPidFile "Dashboard Backend"
        $dashboardPid = $null
    }
}

# NOTE: NiceGUI/Uvicorn may spawn helper/worker processes on Windows.
# Enforcing single-instance semantics by script-path can accidentally kill the real server.
# Opt-in only.
if ($env:CALAMUM_ENFORCE_DASHBOARD_SINGLE_INSTANCE -eq '1') {
    Stop-OrphanInstances "Dashboard Backend" $DashboardScript $dashboardPid
}

if (-not $dashboardPid) {
    Write-Host "    [!] Dashboard Backend not running. Starting..." -ForegroundColor Yellow
    Start-ServiceScript "calamum_dashboard" $DashboardScript $DashboardPidFile
    $dashboardPid = Get-RunningPid $DashboardPidFile
} else {
    Write-Host "    [+] Dashboard Backend is ACTIVE (PID: $dashboardPid)" -ForegroundColor Green
}

# 3. WAIT FOR UPLINK (Only if we just started it, but checking port is safe redundancy)
Write-Host "[*] Verifying Uplink..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(15)
$ready = $false
$portOwnerPid = $null

while ((Get-Date) -lt $deadline) {
    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($listeners) {
            $owning = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
            if ($owning) {
                $portOwnerPid = ($owning | Select-Object -First 1)
                $ready = $true
                break
            }
        }
    } catch {}
    Start-Sleep -Milliseconds 250
}

if (-not $ready) {
    Write-Host "[!] Dashboard did not come online on port $Port. Attempting one restart..." -ForegroundColor Yellow
    Stop-ByPidFile $DashboardPidFile "Dashboard Backend"
    Start-ServiceScript "calamum_dashboard" $DashboardScript $DashboardPidFile

    $deadline = (Get-Date).AddSeconds(15)
    $ready = $false
    $portOwnerPid = $null
    while ((Get-Date) -lt $deadline) {
        try {
            $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
            if ($listeners) {
                $owning = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
                if ($owning) {
                    $portOwnerPid = ($owning | Select-Object -First 1)
                    $ready = $true
                    break
                }
            }
        } catch {}
        Start-Sleep -Milliseconds 250
    }

    if (-not $ready) {
        Write-Host "[!] Dashboard still did not come online on port $Port." -ForegroundColor Red
        exit 1
    }
}

# Reconcile dashboard PID tracking: some servers spawn a child process that owns the port.
if ($portOwnerPid) {
    if ($dashboardPid -and ($dashboardPid -ne $portOwnerPid)) {
        Write-Host "    [!] Dashboard PID mismatch detected (pidfile=$dashboardPid, port_owner=$portOwnerPid). Leaving pidfile unchanged; port owner PID is informational." -ForegroundColor Yellow
    }
    Write-Host "    [+] Dashboard Backend PORT OWNER is ACTIVE (PID: $portOwnerPid)" -ForegroundColor Green
}

# Final single-instance enforcement for the dashboard after port-owner reconciliation.
# Use the current port-owner as expected PID when available; otherwise fallback to pidfile PID.
$expectedDashboardPid = $dashboardPid
if ($portOwnerPid) { $expectedDashboardPid = [int]$portOwnerPid }
Stop-OrphanInstances "Dashboard Backend" $DashboardScript $expectedDashboardPid

# 4. LAUNCH FRONTEND (Edge App Mode)
Write-Host "[*] Launching Ghost Console Interface..." -ForegroundColor Green
$EdgeArgs = @(
    "--app=$Url",
    "--window-size=1100,720",
    "--force-dark-mode",
    "--no-first-run",
    "--disable-session-crashed-bubble",
    "--disable-extensions",
    "--disable-gpu"
)

# Start Edge (detached)
if ($env:CALAMUM_SKIP_BROWSER -eq '1') {
    Write-Host "[*] Browser launch skipped (CALAMUM_SKIP_BROWSER=1)." -ForegroundColor Gray
} else {
    try {
        Start-Process "msedge" -ArgumentList $EdgeArgs
    } catch {
        Write-Host "[!] Could not launch Edge. Open $Url manually." -ForegroundColor Yellow
    }
}

Write-Host "[+] CALAMUM STACK OPERATIONAL." -ForegroundColor Green
