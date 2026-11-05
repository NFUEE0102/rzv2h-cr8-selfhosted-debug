# After editing the firmware in e2 studio (Project -> Build Project, Ctrl+B): post-process the
# ELF, upload it, restart core0 with it, restart OpenOCD if it was running. Disconnect the
# debug session in e2 studio first; the session window (tunnel) can stay open.
. "$PSScriptRoot\common.ps1"
$cfg = Load-Config
$Repo = Repo-Root
$Elf = Join-Path $cfg.ProjectDir "Debug\rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo.elf"
if (-not (Test-Path $Elf)) { Fail "ELF not found: $Elf (build first: Ctrl+B in e2 studio)" }
$age = [int]((Get-Date) - (Get-Item $Elf).LastWriteTime).TotalSeconds
Say "ELF: $Elf (built $([int]($age/60)) min $($age%60) s ago)"

Say "1/3 ELF post-processing"
$tmp = Join-Path $env:TEMP $cfg.Fw
Copy-Item $Elf $tmp -Force
& py -3 (Join-Path $Repo "firmware\tools\patch-elf-phdr.py") $tmp | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "patch-elf-phdr failed" }
Say "    md5 $((Get-FileHash -Algorithm MD5 $tmp).Hash.Substring(0,8).ToLower())"

Say "2/3 upload (scp)"
& scp.exe -o StrictHostKeyChecking=accept-new $tmp "$($script:Evk):/tmp/$($cfg.Fw)"
if ($LASTEXITCODE -ne 0) { Fail "scp failed" }

Say "3/3 restart core0 with it (and OpenOCD if it was running)"
& ssh.exe @(Ssh-Args @("-tt", $script:Evk, "/home/$($cfg.EvkUser)/r8ocd/session.sh", "redeploy", $cfg.Fw))
if ($LASTEXITCODE -ne 0) { Fail "redeploy failed on the EVK" }
Say "done. Back in e2 studio press Debug again."
Start-Sleep -Seconds 3
