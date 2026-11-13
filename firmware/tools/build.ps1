# Windows port of build.sh: build one firmware variant with the headless e2 studio.
#   py -3 is used for the Python tools (Python 3 from python.org; the Store stub does not work).
#   .\build.ps1 core0-demo [-E2Studio "C:\Renesas\rzv\e2studio_v2026-10_fsp_v4.3.0"] [-NoBuild]
# Output: out\<variant>.elf (+ .map, .md5, build log); work tree in build\<variant>\
param(
    [Parameter(Mandatory = $true)][string]$Variant,
    [string]$E2Studio = "",
    [switch]$NoBuild
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Fw = Split-Path -Parent $Here
if (-not $E2Studio) {
    $E2Studio = Get-ChildItem "C:\Renesas\rzv", "C:\Renesas" -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "eclipse\e2studioc.exe") } | Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $E2Studio -or -not (Test-Path "$E2Studio\eclipse\e2studioc.exe")) { throw "e2 studio not found; pass -E2Studio <dir containing eclipse\e2studioc.exe>" }
$Py = (Get-Command py -ErrorAction SilentlyContinue)
if (-not $Py) { throw "Python launcher 'py' not found (install Python 3 from python.org)" }
function PyRun { & py -3 @args; if ($LASTEXITCODE -ne 0) { throw "python tool failed: $($args -join ' ')" } }

$B = Join-Path $Fw "build\$Variant"
$Out = Join-Path $Fw "out"
$Proj = "rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo"
$Cm33 = "rzv2h_rdk_cm33_rpmsg_linux_rtos_demo"
$Cm33Dir = Join-Path $Fw "cm33_demo"
New-Item -ItemType Directory -Force $Out | Out-Null

Write-Host "== [$Variant] assemble work tree"
if (Test-Path $B) { Remove-Item -Recurse -Force $B }
New-Item -ItemType Directory -Force (Split-Path $B) | Out-Null
Copy-Item -Recurse (Join-Path $Fw "base") $B
$Core = 0
switch ($Variant) {
    "core0-pwm"        { }
    "core0-pwm-shared" { PyRun "$Fw\variants\layout_shared.py" $B }
    "core0-pwm-plane"  { PyRun "$Fw\variants\core0_pwm_plane.py" $B }
    "core0-demo"       { PyRun "$Fw\variants\core0_pwm_plane.py" $B; PyRun "$Fw\variants\core0_demo.py" $B }
    "core1-echo"       { $Core = 1; PyRun "$Fw\variants\core1_echo.py" $B }
    "core1-uart"       { $Core = 1; PyRun "$Fw\variants\core1_echo.py" $B; PyRun "$Fw\variants\core1_uart.py" $B }
    "exp-nested-yield" { $Core = 1; PyRun "$Fw\variants\core1_echo.py" $B; PyRun "$Fw\experiments\nested-yield\apply.py" $B }
    "exp-normal-app"   { $Core = 1; PyRun "$Fw\variants\core1_echo.py" $B; PyRun "$Fw\experiments\nested-yield\apply.py" $B --workload 2 }
    default            { throw "unknown variant $Variant" }
}
if ($NoBuild) { Write-Host "work tree ready: $B"; exit 0 }

Write-Host "== [$Variant] packs"
# the generator reads the per-user pack cache, which only a GUI start fills: seed it from the install
# (exit 3 = this e2 studio has never been started by this user, so the cache directory does not exist
# yet. Start it once on the work tree alone - a disposable copy: with no packs the generator fails on
# "Failed to locate component" and strips the include paths from the .cproject it was given, so the
# tracked cm33_demo must not be part of this start - then begin again with the cache in place.)
& py -3 "$Here\seed_pack_cache.py" --e2studio $E2Studio
$SeedRc = $LASTEXITCODE
if ($SeedRc -eq 3) {
    if ($env:CR8_SEED_RETRY) { throw "no pack cache even after a first start of $E2Studio" }
    Write-Host "== [$Variant] first start of this e2 studio for this user: creating its pack cache"
    $Ws0 = Join-Path $env:TEMP ("e2sws_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    $Log0 = Join-Path $Out "$Variant.firststart.log"
    $a0 = @("--launcher.suppressErrors", "-nosplash", "-consoleLog", "-data", $Ws0, "-application", "org.eclipse.cdt.managedbuilder.core.headlessbuild",
            "-import", $B, "-build", "$Proj/Debug", "-no-indexer")
    $p0 = Start-Process -FilePath "$E2Studio\eclipse\e2studioc.exe" -ArgumentList $a0 -NoNewWindow -PassThru -RedirectStandardOutput $Log0 -RedirectStandardError "$Log0.err"
    if (-not $p0.WaitForExit(600000)) { $p0.Kill() }
    Remove-Item "$Log0.err" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Ws0 -ErrorAction SilentlyContinue
    $env:CR8_SEED_RETRY = "1"
    try { & $MyInvocation.MyCommand.Path -Variant $Variant -E2Studio $E2Studio } finally { Remove-Item Env:CR8_SEED_RETRY -ErrorAction SilentlyContinue }
    exit $LASTEXITCODE
}
elseif ($SeedRc -ne 0) { throw "python tool failed: seed_pack_cache.py" }
PyRun "$Here\patch_packs.py" --e2studio $E2Studio

Write-Host "== [$Variant] headless e2 studio build (this takes about a minute)"
$Ws = Join-Path $env:TEMP ("e2sws_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$Log = Join-Path $Out "$Variant.build.log"
# --launcher.suppressErrors: a generator failure otherwise ends in a modal "Java was started but returned
# exit code=1" dialog that blocks until someone clicks it; the log carries the error anyway.
$e2sArgs = @("--launcher.suppressErrors", "-nosplash", "-consoleLog", "-data", $Ws, "-application", "org.eclipse.cdt.managedbuilder.core.headlessbuild",
             "-import", $Cm33Dir, "-import", $B, "-build", "$Cm33/Debug", "-build", "$Proj/Debug", "-no-indexer")
$p = Start-Process -FilePath "$E2Studio\eclipse\e2studioc.exe" -ArgumentList $e2sArgs -NoNewWindow -PassThru -RedirectStandardOutput $Log -RedirectStandardError "$Log.err"
$null = $p.Handle   # keep the handle so ExitCode is available without -Wait
if (-not $p.WaitForExit(1500000)) { $p.Kill(); Write-Host "   e2studioc killed after 25 min (stuck?)" }
Get-Content "$Log.err" -ErrorAction SilentlyContinue | Add-Content $Log; Remove-Item "$Log.err" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $Ws -ErrorAction SilentlyContinue
$finished = (Select-String -Path $Log -Pattern "Build Finished" | Measure-Object).Count
# On a fresh tree the headless builder first runs "make clean", which fails with
# "No rule to make target 'clean'" and is reported as a Build Failed of its own: noise.
$cleanNoise = (Select-String -Path $Log -Pattern "No rule to make target 'clean'" | Measure-Object).Count
$failed = (Select-String -Path $Log -Pattern "Build Failed" | Measure-Object).Count - $cleanNoise
Write-Host "   e2studioc rc=$($p.ExitCode) finished=$finished/2 failed=$failed log=$Log"
Select-String -Path $Log -Pattern "error:|undefined reference|cannot find|multiple definition" | Where-Object { $_.Line -notmatch "manifest file error" } | Select-Object -First 20 | ForEach-Object { Write-Host "   $($_.Line)" }
$Elf = Join-Path $B "Debug\$Proj.elf"
if ($failed -gt 0 -or $finished -lt 2 -or -not (Test-Path $Elf)) { throw "BUILD FAILED ($Log)" }

Write-Host "== [$Variant] regeneration + pack-patch check"
PyRun "$Here\check_regen.py" $B

Write-Host "== [$Variant] ELF post-processing"
PyRun "$Here\patch-elf-phdr.py" $Elf
if ($Core -eq 1) {
    PyRun "$Here\null_phdr_at.py" $Elf 0x081BFFFC
    # give the core1 project its own Eclipse name so it can sit next to the core0 project in one
    # workspace (the artifact name, Debug\<core0 name>.elf, is unchanged)
    # (PowerShell variable names are case-insensitive: this must not be called $proj, it would clobber $Proj)
    $projFile = Join-Path $B ".project"
    (Get-Content $projFile -Raw).Replace("<name>$Proj</name>", "<name>rzv2h_rdk_cr8_core1_rpmsg_linux_rtos_demo</name>") | Set-Content $projFile -Encoding UTF8
}
Copy-Item $Elf (Join-Path $Out "$Variant.elf") -Force
Copy-Item (Join-Path $B "Debug\$Proj.map") (Join-Path $Out "$Variant.map") -Force -ErrorAction SilentlyContinue
$md5 = (Get-FileHash -Algorithm MD5 (Join-Path $Out "$Variant.elf")).Hash.ToLower()
"$md5  $Variant.elf" | Set-Content (Join-Path $Out "$Variant.md5")
Write-Host "== [$Variant] done -> $Out\$Variant.elf  (md5 $($md5.Substring(0,8)))"
