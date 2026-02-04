# TAG: GHOST_CONSOLE_LAUNCHER
# Launcher for Calamum Ops Widget (Ghost Console)
# Bypass pythonnet dependency by using Edge in Application Mode.

$ScriptPath = Join-Path $PSScriptRoot "src\ops_dashboard.py"
# Calculate root from "projects/calamum-moltbook-observer" (2 levels down)
$RepoRoot = Resolve-Path "$PSScriptRoot\..\.." 
$VenvPython = Join-Path $RepoRoot ".venv-core\Scripts\python.exe"
$Port = 8899
$Url = "http://localhost:$Port"
$BackendProcessIdFile = Join-Path $PSScriptRoot "ghost_console.pid"
$BackendLogDir = Join-Path $RepoRoot "logs"
$BackendStdoutLog = Join-Path $BackendLogDir "ghost_console_backend.stdout.log"
$BackendStderrLog = Join-Path $BackendLogDir "ghost_console_backend.stderr.log"

Write-Host "[*] Initializing Ghost Console V2..." -ForegroundColor Green

function Stop-OldGhostConsole {
    param(
        [int]$Port,
        [string]$BackendProcessIdFile
    )

    # 1) Stop prior instance tracked by PID file (reliable for hidden windows)
    if (Test-Path $BackendProcessIdFile) {
        $OldProcessIdRaw = (Get-Content $BackendProcessIdFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($OldProcessIdRaw -match '^\d+$') {
            $OldProcessId = [int]$OldProcessIdRaw
            $OldProc = Get-Process -Id $OldProcessId -ErrorAction SilentlyContinue
            if ($OldProc) {
                Write-Host "[!] Stopping previous backend (PID: $OldProcessId)..." -ForegroundColor Yellow
                Stop-Process -Id $OldProcessId -Force -ErrorAction SilentlyContinue
                Start-Sleep -Milliseconds 300
            }
        }
        Remove-Item $BackendProcessIdFile -Force -ErrorAction SilentlyContinue
    }

    # 2) If port is still in use, stop the owning process
    # 2a) Stop any python process that appears to be running this dashboard (command line match)
    try {
        $dashProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -match '^python(\.exe)?$' -and
                $_.CommandLine -and
                ($_.CommandLine -match 'calamum-moltbook-observer') -and
                ($_.CommandLine -match 'ops_dashboard\.py')
            }
        foreach ($p in $dashProcs) {
            Write-Host "[!] Stopping dashboard python (PID: $($p.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {
        # best-effort
    }

    # 2b) If port is still in use, stop the owning process(es) until freed
    try {
        $deadline = (Get-Date).AddSeconds(8)
        while ((Get-Date) -lt $deadline) {
            $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
            if (-not $listeners) { break }

            $owning = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($processId in $owning) {
                if ($processId) {
                    Write-Host "[!] Port $Port in use. Stopping listener PID: $processId..." -ForegroundColor Yellow
                    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                }
            }
            Start-Sleep -Milliseconds 500
        }
    } catch {
        # If Get-NetTCPConnection isn't available, we'll just proceed; handshake below will catch failures.
    }
}

function Lock-EdgeAppWindow {
    param(
        [int]$ProcessId,
        [string]$WindowTitle
    )

    # Best-effort: remove resize/maximize styles from the Edge app window.
    # Primary method: wait for the Edge process MainWindowHandle.
    # Fallback: FindWindow by title.
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32 {
  [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
  [DllImport("user32.dll", SetLastError=true)] public static extern bool IsWindow(IntPtr hWnd);
  [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
  [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
  [DllImport("user32.dll", SetLastError=true)] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
  public const int GWL_STYLE = -16;
  public const long WS_THICKFRAME = 0x00040000L;
  public const long WS_MAXIMIZEBOX = 0x00010000L;
  public const long WS_SIZEBOX = 0x00040000L;
  public const long WS_MINIMIZEBOX = 0x00020000L;
  public const uint SWP_NOMOVE = 0x0002;
  public const uint SWP_NOSIZE = 0x0001;
  public const uint SWP_NOZORDER = 0x0004;
  public const uint SWP_FRAMECHANGED = 0x0020;
}
"@ -ErrorAction SilentlyContinue | Out-Null

    $deadline = (Get-Date).AddSeconds(6)
    while ((Get-Date) -lt $deadline) {
        $hWnd = [IntPtr]::Zero
        try {
            if ($ProcessId -gt 0) {
                $p = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
                if ($p -and $p.MainWindowHandle -and $p.MainWindowHandle -ne 0) {
                    $hWnd = [IntPtr]$p.MainWindowHandle
                }
            }
        } catch {
            # ignore
        }
        if ($hWnd -eq [IntPtr]::Zero -and $WindowTitle) {
            $hWnd = [Win32]::FindWindow($null, $WindowTitle)
        }
        if ($hWnd -ne [IntPtr]::Zero -and [Win32]::IsWindow($hWnd)) {
            $stylePtr = [Win32]::GetWindowLongPtr($hWnd, [Win32]::GWL_STYLE)
            $style = $stylePtr.ToInt64()
            $style = $style -band (-bnot ([Win32]::WS_THICKFRAME))
            $style = $style -band (-bnot ([Win32]::WS_MAXIMIZEBOX))
            [Win32]::SetWindowLongPtr($hWnd, [Win32]::GWL_STYLE, [IntPtr]$style) | Out-Null
            [Win32]::SetWindowPos($hWnd, [IntPtr]::Zero, 0, 0, 0, 0, [Win32]::SWP_NOMOVE -bor [Win32]::SWP_NOSIZE -bor [Win32]::SWP_NOZORDER -bor [Win32]::SWP_FRAMECHANGED) | Out-Null
            Write-Host "[i] Locked app window (no resize/maximize)." -ForegroundColor DarkGray
            break
        }
        Start-Sleep -Milliseconds 250
    }
}

# 1. Stop any prior Ghost Console backend so changes actually take effect
Stop-OldGhostConsole -Port $Port -BackendProcessIdFile $BackendProcessIdFile

# Confirm port is free before starting a new backend
try {
    $existingListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existingListener -and $existingListener.OwningProcess) {
        $existingProcessId = [int]$existingListener.OwningProcess
        $cmd = ''
        try {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$existingProcessId" | Select-Object -ExpandProperty CommandLine)
        } catch { }
        Write-Host "[X] Port $Port is still in use by PID $existingProcessId. Refusing to start a new backend." -ForegroundColor Red
        if ($cmd) {
            Write-Host "[i] Owner command line: $cmd" -ForegroundColor DarkGray
        }
        Write-Host "[i] Close any open Ghost Console windows and rerun this launcher." -ForegroundColor DarkGray
        exit 1
    }
} catch {
    # best-effort; if we can't check, proceed and let bind errors surface.
}

# 2. Start the Backend Server (Hidden Window)
Write-Host "[*] Starting Operation Server (Background) on Port $Port..." -ForegroundColor Green
# Redirect stdout/stderr so hidden backend errors are visible.
try {
    New-Item -ItemType Directory -Force -Path $BackendLogDir | Out-Null
} catch {
    # best-effort
}
try {
    $Job = Start-Process -FilePath $VenvPython -ArgumentList "-u", "$ScriptPath" -WindowStyle Hidden -PassThru -RedirectStandardOutput $BackendStdoutLog -RedirectStandardError $BackendStderrLog
} catch {
    # Fallback if redirection isn't supported in this host context.
    $Job = Start-Process -FilePath $VenvPython -ArgumentList "-u", "$ScriptPath" -WindowStyle Hidden -PassThru
}

# 3. Wait for Server Handshake (port is listening)
Write-Host "[*] Waiting for uplink..." -ForegroundColor Cyan
$Ready = $false
$ListenerProcessId = $null
$Deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $Deadline) {
    try {
        $Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($Listeners) {
            $CandidateIds = $Listeners | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($processId in $CandidateIds) {
                if (-not $processId) { continue }
                $cmd = ''
                try {
                    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$processId" | Select-Object -ExpandProperty CommandLine)
                } catch { }
                if ($cmd -and ($cmd -match 'calamum-moltbook-observer') -and ($cmd -match 'ops_dashboard\.py')) {
                    $ListenerProcessId = [int]$processId
                    $Ready = $true
                    break
                }
            }
            if ($Ready) { break }
        }
    } catch {
        # ignore
    }
    Start-Sleep -Milliseconds 250
}

if (-not $Ready) {
    # If something else owns the port, report it explicitly.
    try {
        $Other = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($Other -and $Other.OwningProcess) {
            Write-Host "[X] Port $Port is listening, but the listener does not look like ops_dashboard.py (listener PID: $($Other.OwningProcess))." -ForegroundColor Red
        } else {
            Write-Host "[X] Backend did not begin listening on port $Port." -ForegroundColor Red
        }
    } catch {
        Write-Host "[X] Backend did not begin listening on port $Port." -ForegroundColor Red
    }
    Write-Host "[i] Tip: if a zombie process is holding the port, rerun this launcher." -ForegroundColor DarkGray
    try { Stop-Process -Id $Job.Id -Force -ErrorAction SilentlyContinue } catch { }
    exit 1
}

# Record the listener PID (may differ from Start-Process PID)
if ($ListenerProcessId) {
    Set-Content -Path $BackendProcessIdFile -Value $ListenerProcessId -Encoding ASCII
}

# 4. Launch Frontend (Edge App Mode)
# This creates a window without tabs/address bar, looking like a native app.
Write-Host "[*] Launching Interface..." -ForegroundColor Green

# Optional hardening flags for stability.
#
# Observed symptom: Edge app-mode window appears to "blank" and then we see a fresh
# `client_boot` with `nav_type: navigate` (a real navigation). That pattern commonly
# occurs when the renderer process crashes / is killed and the tab is recreated.
#
# In a fixed-size kiosk-style appliance UI, software rendering is usually fine and
# tends to be more stable on some Windows GPU/driver combos.
#
# Controls:
#   - CALAMUM_EDGE_DISABLE_GPU=1  -> force software rendering
#   - CALAMUM_EDGE_ENABLE_GPU=1   -> prefer GPU rendering (overrides default)
#   - CALAMUM_EDGE_EXTRA_ARGS     -> space-separated extra flags
$EdgeArgs = @(
    "--app=$Url",
    "--window-size=1100,720",
    "--force-dark-mode",
    "--no-first-run",
    "--disable-session-crashed-bubble",
    "--disable-extensions",
    "--disable-features=CalculateNativeWinOcclusion"
)

# Default: disable GPU unless explicitly enabled. Explicit disable always wins.
$DisableGpu = $true
if ($env:CALAMUM_EDGE_ENABLE_GPU -and $env:CALAMUM_EDGE_ENABLE_GPU -ne '0') {
    $DisableGpu = $false
}
if ($env:CALAMUM_EDGE_DISABLE_GPU -and $env:CALAMUM_EDGE_DISABLE_GPU -ne '0') {
    $DisableGpu = $true
}
if ($DisableGpu) {
    $EdgeArgs += "--disable-gpu"
    $EdgeArgs += "--use-gl=swiftshader"
}

if ($env:CALAMUM_EDGE_EXTRA_ARGS) {
    try {
        $extra = ($env:CALAMUM_EDGE_EXTRA_ARGS -split '\s+') | Where-Object { $_ -and $_.Trim().Length -gt 0 }
        if ($extra) { $EdgeArgs += $extra }
    } catch {
        # best-effort
    }
}

try {
    $EdgeProc = Start-Process "msedge" -ArgumentList $EdgeArgs -PassThru
} catch {
    $EdgeProc = $null
    Start-Process "msedge" -ArgumentList $EdgeArgs
}

# Try to lock the window to a fixed size (best-effort)
if ($EdgeProc -and $EdgeProc.Id) {
    Lock-EdgeAppWindow -ProcessId ([int]$EdgeProc.Id) -WindowTitle "CALAMUM OPS V2"
} else {
    Lock-EdgeAppWindow -ProcessId 0 -WindowTitle "CALAMUM OPS V2"
}

Write-Host "[+] GHOST CONSOLE ONLINE." -ForegroundColor Green
Write-Host "[i] The backend is running in the background (PID: $($Job.Id))."
