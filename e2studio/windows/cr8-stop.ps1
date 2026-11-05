# Tear down: close any open EVK session window (its hang-up trap stops OpenOCD gracefully);
# if none is open, stop OpenOCD on the EVK directly.
. "$PSScriptRoot\common.ps1"
$cfg = Load-Config
$procs = @(Find-SessionProcesses)
if ($procs.Count -gt 0) {
    Say "closing $($procs.Count) EVK session window(s); OpenOCD stops on the board"
    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 3
} else {
    Say "no session window open; stopping OpenOCD on the EVK directly (password prompts may follow)"
    & ssh.exe @(Ssh-Args @("-tt", $script:Evk, "/home/$($cfg.EvkUser)/r8ocd/session.sh", "stop"))
}
Say "done"
Start-Sleep -Seconds 2
