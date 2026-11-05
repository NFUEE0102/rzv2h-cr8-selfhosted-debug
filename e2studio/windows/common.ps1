# Shared pieces for the Windows launchers. Windows OpenSSH has no ControlMaster, so one debug
# session = one `ssh -tt -L ... session.sh start` connection that carries the tunnel, the sudo
# prompt and OpenOCD's lifetime (see debug/session.sh). Without an SSH key each ssh/scp asks
# for the password; install-host.ps1 offers to set a key up.
#
# Config: %APPDATA%\cr8-debug\config.json  (created by install-host.ps1)
#   EvkHost, EvkUser, Fw, ProjectDir, E2Studio (install dir), Workspace
$ErrorActionPreference = "Stop"
$script:ConfigPath = Join-Path $env:APPDATA "cr8-debug\config.json"
$script:Port = 3333
$script:Beacon = 3335

function Say([string]$m)  { Write-Host "[cr8] $m" -ForegroundColor Cyan }
function Warn([string]$m) { Write-Host "[cr8] $m" -ForegroundColor Yellow }
function Fail([string]$m) { Write-Host "[cr8] $m" -ForegroundColor Red; Read-Host "Enter to close" | Out-Null; exit 1 }

function Load-Config {
    if (-not (Test-Path $script:ConfigPath)) { Fail "no config at $script:ConfigPath - run install-host.ps1 first" }
    $c = Get-Content $script:ConfigPath -Raw | ConvertFrom-Json
    $script:Evk = "$($c.EvkUser)@$($c.EvkHost)"
    return $c
}

function Repo-Root { (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

function Ssh-Args([string[]]$extra) {
    @("-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=15") + $extra
}

function Test-Tcp([string]$addr, [int]$port, [int]$timeoutMs = 500) {   # ($host is reserved in PowerShell)
    try {
        $c = New-Object Net.Sockets.TcpClient
        $r = $c.BeginConnect($addr, $port, $null, $null)
        if (-not $r.AsyncWaitHandle.WaitOne($timeoutMs)) { $c.Close(); return $false }
        $c.EndConnect($r); $c.Close(); return $true
    } catch { return $false }
}

# The remote beacon answers "READY" on 127.0.0.1:3335 once OpenOCD is up; through the tunnel
# a local connect to 3335 succeeds only then. (We never probe 3333: OpenOCD logs every
# connect-and-drop as a rejected gdb connection.)
function Wait-Ready([int]$seconds = 90) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (Test-Tcp "127.0.0.1" $script:Beacon 400) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Find-SessionProcesses {
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" | Where-Object { $_.CommandLine -match "session\.sh start" }
}
