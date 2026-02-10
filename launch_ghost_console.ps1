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
                    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
                    # Ensure it's dead
                    Start-Sleep -Milliseconds 200
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
    
    try {
        $proc = Start-Process -FilePath $VenvPython `
            -ArgumentList (@("-u", $scriptPath) + $argsList) `
            -WindowStyle Hidden `
            -PassThru `
            -RedirectStandardOutput $logOut `
            -RedirectStandardError $logErr
            
        if ($proc -and $proc.Id) {
            Set-Content -Path $pidFile -Value $proc.Id -Encoding ASCII
            Write-Host "    -> Started (PID: $($proc.Id))" -ForegroundColor Green
        } else {
            Write-Host "    [!] Failed to start $name" -ForegroundColor Red
        }
    } catch {
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
    foreach ($procId in $pids) {
        if ($expectedPid -and ($procId -eq $expectedPid)) {
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
if (-not $agentPid) {
    Write-Host "    [!] Observer Agent not running. Starting..." -ForegroundColor Yellow
    Start-ServiceScript "calamum_agent" $AgentScript $AgentPidFile @("--mode", "canary", "--interval-sec", "2.0")
} else {
    Write-Host "    [+] Observer Agent is ACTIVE (PID: $agentPid)" -ForegroundColor Green
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

# Final single-instance enforcement for the dashboard after port-owner reconciliation (opt-in only).
if ($env:CALAMUM_ENFORCE_DASHBOARD_SINGLE_INSTANCE -eq '1') {
    Stop-OrphanInstances "Dashboard Backend" $DashboardScript $dashboardPid
}

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
try {
    Start-Process "msedge" -ArgumentList $EdgeArgs
} catch {
    Write-Host "[!] Could not launch Edge. Open $Url manually." -ForegroundColor Yellow
}

Write-Host "[+] CALAMUM STACK OPERATIONAL." -ForegroundColor Green
