# One click: SSH session to the EVK (tunnel :3333 + :3335, firmware check, OpenOCD) in its own
# window, then e2 studio. Closing e2 studio closes the session window, which stops OpenOCD on
# the EVK gracefully (debug/session.sh traps the hang-up).
#   cr8-debug.ps1            full flow (desktop shortcut)
#   cr8-debug.ps1 -NoIde     bring the session up, verify READY, tear down (self-test)
param([switch]$NoIde)
. "$PSScriptRoot\common.ps1"
$cfg = Load-Config

if (Find-SessionProcesses) { Fail "a CR8 debug session is already open (ssh window). Close it or run cr8-stop.ps1." }
if (Test-Tcp "127.0.0.1" $script:Port 200) { Fail "port $script:Port is already in use on this PC" }

Say "1/3 opening the EVK session ($script:Evk): tunnel + firmware check + OpenOCD"
Say "    (the new window asks for the SSH password, then the EVK sudo password, unless a key is set up)"
$sshArgs = Ssh-Args @("-tt", "-L", "$($script:Port):127.0.0.1:$($script:Port)", "-L", "$($script:Beacon):127.0.0.1:$($script:Beacon)",
                      $script:Evk, "/home/$($cfg.EvkUser)/r8ocd/session.sh", "start", $cfg.Fw)
$sess = Start-Process -FilePath "ssh.exe" -ArgumentList $sshArgs -PassThru
Say "2/3 waiting for READY (up to 90 s)"
if (-not (Wait-Ready 90)) {
    if ($sess.HasExited) { Fail "the session window closed before READY (wrong password? EVK offline? see its output)" }
    Fail "no READY within 90 s - check the session window"
}
Say "    tunnel OK, OpenOCD listening"

if ($NoIde) {
    Say "3/3 (-NoIde) self-test passed; closing the session"
    Stop-Process -Id $sess.Id -Force -ErrorAction SilentlyContinue
    exit 0
}

Say "3/3 e2 studio, workspace $($cfg.Workspace)"
Say "    Run -> Debug Configurations -> GDB Hardware Debugging -> 'CR8 core0 via OpenOCD dmem'"
Say "    leave with Disconnect; closing e2 studio ends the EVK session"
$e2s = Start-Process -FilePath (Join-Path $cfg.E2Studio "eclipse\e2studio.exe") -ArgumentList @("-data", $cfg.Workspace) -PassThru
$e2s.WaitForExit()
Say "e2 studio closed -> ending the EVK session (OpenOCD stops on the board)"
Stop-Process -Id $sess.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
