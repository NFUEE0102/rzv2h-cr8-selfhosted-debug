# Build CR8DebugApp.exe (single file, no console) from cr8_debug_app.py with PyInstaller.
#   powershell -ExecutionPolicy Bypass -File e2studio\windows\build-exe.ps1
# Output: CR8DebugApp.exe in the repository root (gitignored; attach it to the GitHub release).
# The EXE must be run from inside the repository folder (it needs debug/, firmware/, e2studio/).
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = (Resolve-Path (Join-Path $Here "..\..")).Path
& py -3 -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { & py -3 -m pip install pyinstaller; if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" } }
& py -3 -c "import paramiko" 2>$null
if ($LASTEXITCODE -ne 0) { & py -3 -m pip install paramiko }
$Work = Join-Path $env:TEMP "cr8-pyinstaller"
& py -3 -m PyInstaller --noconfirm --onefile --windowed --name CR8DebugApp `
    --distpath $Repo --workpath (Join-Path $Work "build") --specpath $Work `
    --hidden-import paramiko (Join-Path $Here "cr8_debug_app.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$exe = Join-Path $Repo "CR8DebugApp.exe"
Write-Host ("built {0}  ({1:N1} MB, md5 {2})" -f $exe, ((Get-Item $exe).Length / 1MB), (Get-FileHash -Algorithm MD5 $exe).Hash.Substring(0, 8).ToLower())
