# Windows host setup, run once from a clone of this repo (PowerShell 5.1 or 7):
#   powershell -ExecutionPolicy Bypass -File e2studio\windows\install-host.ps1
# * asks for the EVK address etc. and writes %APPDATA%\cr8-debug\config.json
# * checks ssh.exe / scp.exe (Windows OpenSSH), Python 3 (py launcher), e2 studio
# * optionally creates an SSH key and installs it on the EVK (one password prompt, then none)
# * builds the demo firmware project with the headless e2 studio if it is not built yet
# * drops the launch configuration into the project (gdb = e2 studio's arm-none-eabi-gdb.exe)
# * imports the project into the workspace (headless) and puts three shortcuts on the Desktop
# * deploys the freshly built firmware to the EVK
# Re-running is safe. -NoBuild / -NoDesktop / -NoDeploy skip those steps.
param([switch]$NoBuild, [switch]$NoDesktop, [switch]$NoDeploy)
. "$PSScriptRoot\common.ps1"
$Repo = Repo-Root
$ConfigDir = Split-Path $script:ConfigPath

function Ask([string]$prompt, [string]$default) {
    $a = Read-Host "$prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($a)) { $default } else { $a }
}

# ---- config ---------------------------------------------------------------------------------
if (Test-Path $script:ConfigPath) {
    $cfg = Get-Content $script:ConfigPath -Raw | ConvertFrom-Json
    Say "config: $script:ConfigPath (delete it to be asked again)"
} else {
    Say "No config yet. A few questions:"
    $e2sDefault = Get-ChildItem "C:\Renesas\rzv", "C:\Renesas" -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "eclipse\e2studio.exe") } | Select-Object -First 1 -ExpandProperty FullName
    $cfg = [pscustomobject]@{
        EvkHost    = Ask "EVK IP address" "192.168.1.177"   # ci:allow-ip
        EvkUser    = Ask "EVK user" "ubuntu"
        Fw         = Ask "firmware file name on the EVK" "cr8_demo.elf"
        ProjectDir = Ask "e2 studio project directory" (Join-Path $Repo "firmware\build\core0-demo")
        E2Studio   = Ask "e2 studio install dir (contains eclipse\e2studio.exe)" $(if ($e2sDefault) { $e2sDefault } else { "C:\Renesas\rzv\e2studio_v2025-01_fsp_v3.1.0" })
        Workspace  = Ask "e2 studio workspace" (Join-Path $env:USERPROFILE "cr8dbg-workspace")
    }
    New-Item -ItemType Directory -Force $ConfigDir | Out-Null
    $cfg | ConvertTo-Json | Set-Content $script:ConfigPath -Encoding UTF8
    Say "saved $script:ConfigPath"
}
$Evk = "$($cfg.EvkUser)@$($cfg.EvkHost)"
Say "  EVK=$Evk  Fw=$($cfg.Fw)"
Say "  ProjectDir=$($cfg.ProjectDir)"
Say "  E2Studio=$($cfg.E2Studio)  Workspace=$($cfg.Workspace)"

# ---- tools ----------------------------------------------------------------------------------
Say "1/6 tools"
foreach ($t in "ssh.exe", "scp.exe") { if (-not (Get-Command $t -ErrorAction SilentlyContinue)) { Fail "$t not found: install 'OpenSSH Client' (Settings > Apps > Optional features)" } }
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { Fail "Python launcher 'py' not found: install Python 3 from python.org (not the Store stub)" }
& py -3 -c "import paramiko, tkinter" 2>$null
if ($LASTEXITCODE -ne 0) { Say "  installing paramiko (SSH library for the clickable app)"; & py -3 -m pip install -q paramiko; if ($LASTEXITCODE -ne 0) { Warn "  pip install paramiko failed; CR8 Debug App will not run" } }
if (-not (Test-Path (Join-Path $cfg.E2Studio "eclipse\e2studio.exe"))) { Fail "e2 studio not found at $($cfg.E2Studio)" }
$gdb = Get-ChildItem (Join-Path $cfg.E2Studio "toolchains") -Recurse -Filter "arm-none-eabi-gdb.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if (-not $gdb) { Fail "arm-none-eabi-gdb.exe not found under $($cfg.E2Studio)\toolchains" }
Say "  gdb: $gdb"

# ---- SSH key (optional) ---------------------------------------------------------------------
Say "2/6 SSH key to the EVK"
$key = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
$keyOk = $false
if (Test-Path $key) {
    & ssh.exe -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new $Evk true 2>$null
    if ($LASTEXITCODE -eq 0) { $keyOk = $true; Say "  key already works" }
}
if (-not $keyOk) {
    $a = Ask "Set up an SSH key so no password is asked later? (y/N)" "N"
    if ($a -match "^[yY]") {
        if (-not (Test-Path $key)) { & ssh-keygen.exe -t ed25519 -N '""' -f $key -q }
        Say "  installing the public key on the EVK (password prompt once)"
        $pub = Get-Content "$key.pub" -Raw
        $pub.Trim() | & ssh.exe -o StrictHostKeyChecking=accept-new $Evk "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
        if ($LASTEXITCODE -eq 0) { Say "  key installed" } else { Warn "  key setup failed; passwords will be asked" }
    } else { Say "  skipped; each ssh/scp will ask for the password" }
}

# ---- firmware project -----------------------------------------------------------------------
Say "3/6 firmware project"
$Elf = Join-Path $cfg.ProjectDir "Debug\rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo.elf"
if ((Test-Path (Join-Path $cfg.ProjectDir ".project")) -and (Test-Path $Elf)) { Say "  already built" }
elseif ($NoBuild) { Warn "  not built and -NoBuild given; cr8-redeploy will not work until it is" }
else {
    $variant = Split-Path $cfg.ProjectDir -Leaf
    Say "  building variant '$variant' (patches the FSP packs first, ~1 min)"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Repo "firmware\tools\build.ps1") $variant -E2Studio $cfg.E2Studio
    if ($LASTEXITCODE -ne 0) { Fail "firmware build failed" }
}

# ---- launch configuration -------------------------------------------------------------------
Say "4/6 launch configuration into the project (gdb = $gdb)"
$launchSrc = Join-Path $Repo "e2studio\CR8 core0 via OpenOCD dmem.launch"
$launchDst = Join-Path $cfg.ProjectDir "CR8 core0 via OpenOCD dmem.launch"
(Get-Content $launchSrc -Raw) -replace 'org\.eclipse\.cdt\.dsf\.gdb\.DEBUG_NAME" value="gdb-multiarch"', ('org.eclipse.cdt.dsf.gdb.DEBUG_NAME" value="' + ($gdb -replace '\\', '\\') + '"') |
    Set-Content $launchDst -Encoding UTF8
Copy-Item (Join-Path $Repo "examples\demo_servo\DEMO.zh-TW.md") $cfg.ProjectDir -Force -ErrorAction SilentlyContinue

# ---- workspace ------------------------------------------------------------------------------
Say "5/6 e2 studio workspace $($cfg.Workspace)"
$wsProj = Join-Path $cfg.Workspace ".metadata\.plugins\org.eclipse.core.resources\.projects\rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo"
if (Test-Path $wsProj) { Say "  project already in the workspace" }
else {
    New-Item -ItemType Directory -Force $cfg.Workspace | Out-Null
    $log = "$($cfg.Workspace)-import.log"
    $p = Start-Process -FilePath (Join-Path $cfg.E2Studio "eclipse\e2studioc.exe") -ArgumentList @(
        "-nosplash", "-consoleLog", "-data", $cfg.Workspace, "-application", "org.eclipse.cdt.managedbuilder.core.headlessbuild",
        "-import", (Join-Path $Repo "firmware\cm33_demo"), "-import", $cfg.ProjectDir, "-no-indexer") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $log
    if (Test-Path $wsProj) { Say "  imported" } else { Warn "  headless import did not register the project (see $log); use File -> Import in the GUI" }
}

# ---- desktop shortcuts ----------------------------------------------------------------------
Say "6/6 desktop shortcuts"
if ($NoDesktop) { Say "  skipped" } else {
    $desk = [Environment]::GetFolderPath("Desktop")
    $wsh = New-Object -ComObject WScript.Shell
    $pyw = & py -3 -c "import sys,os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"
    $app = $wsh.CreateShortcut((Join-Path $desk "CR8 Debug App.lnk"))
    $app.TargetPath = $pyw
    $app.Arguments = "`"$PSScriptRoot\cr8_debug_app.py`""
    $app.WorkingDirectory = $PSScriptRoot
    $app.IconLocation = "shell32.dll,165"
    $app.Save()
    foreach ($s in @(@{n = "CR8 Debug (e2 studio)"; f = "cr8-debug.ps1"; i = 220}, @{n = "CR8 Debug STOP"; f = "cr8-stop.ps1"; i = 131}, @{n = "CR8 Redeploy"; f = "cr8-redeploy.ps1"; i = 238})) {
        $lnk = $wsh.CreateShortcut((Join-Path $desk "$($s.n).lnk"))
        $lnk.TargetPath = "powershell.exe"
        $lnk.Arguments = "-ExecutionPolicy Bypass -NoProfile -File `"$PSScriptRoot\$($s.f)`""
        $lnk.WorkingDirectory = $PSScriptRoot
        $lnk.IconLocation = "shell32.dll,$($s.i)"
        $lnk.Save()
    }
    Say "  $desk`: CR8 Debug App (one window: login, start, e2 studio, stop) + CR8 Debug (e2 studio) / STOP / Redeploy (ssh.exe variants)"
}

# ---- deploy ---------------------------------------------------------------------------------
if ($NoDeploy) { Say "deploy skipped (-NoDeploy)" }
elseif (Test-Path $Elf) {
    Say "deploying the firmware built here to the EVK (so sources resolve in e2 studio)"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "cr8-redeploy.ps1")
}
Say "done. Click 'CR8 Debug App' on the Desktop: it installs the A55 side itself on first use."
