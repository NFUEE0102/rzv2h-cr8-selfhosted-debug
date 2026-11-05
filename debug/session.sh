#!/bin/bash
# One SSH session = one debug session. Installed to ~/r8ocd/session.sh by install-on-evk.sh
# and driven by the Windows launchers (Windows OpenSSH has no ControlMaster, so everything a
# session needs runs inside the single `ssh -tt -L 3333:... session.sh start` connection):
#
#   session.sh start [fw.elf]   ask the sudo password once on this tty, start the firmware if
#                               core0 is offline, start OpenOCD, open a READY beacon on
#                               127.0.0.1:3335, then wait. When the SSH connection drops
#                               (window closed, Ctrl-C) OpenOCD is stopped gracefully.
#   session.sh stop             resume every core and shut OpenOCD down.
#   session.sh redeploy fw.elf  /tmp/fw.elf was uploaded (already phdr-patched): stop OpenOCD,
#                               install it, restart core0, start OpenOCD again.
set -u
DIR=$(cd "$(dirname "$0")" && pwd)
MODE=${1:-start}
FW=${2:-cr8_demo.elf}
PORT=3333
BEACON=3335
PW=""

sudo_() { printf '%s\n' "$PW" | sudo -S -p '' "$@"; }
get_pw() {
    if sudo -n true 2>/dev/null; then sudo_() { sudo "$@"; }; return; fi
    read -r -s -p "sudo password for $USER on the EVK: " PW < /dev/tty 2> /dev/tty; echo > /dev/tty
    printf '%s\n' "$PW" | sudo -S -p '' -v 2>/dev/null || { echo "wrong sudo password"; exit 1; }
}
ocd_running() { pgrep -x openocd >/dev/null; }
ocd_start() {
    : > "$DIR/ocd.log"
    sudo_ sh -c "cd $DIR && nohup ./r8ocd.sh >> ocd.log 2>&1 &"
    for _ in $(seq 1 25); do
        grep -q "Listening on port $PORT" "$DIR/ocd.log" 2>/dev/null && break
        grep -qE 'Refusing|Error|not found' "$DIR/ocd.log" 2>/dev/null && { grep -v '^Debug' "$DIR/ocd.log" | tail -5; return 1; }
        sleep 1
    done
    grep -q "Listening on port $PORT" "$DIR/ocd.log" && ocd_running
}
ocd_stop() {
    ocd_running || return 0
    printf 'targets rzv2h.cr8_0\nresume\ntargets rzv2h.cr8_1\nresume\nshutdown\n' | timeout 10 nc -q2 127.0.0.1 4444 >/dev/null 2>&1
    for _ in 1 2 3 4 5; do ocd_running || return 0; sleep 1; done
    sudo_ pkill -TERM openocd; sleep 1
    ocd_running && sudo_ pkill -KILL openocd
    return 0
}
fw_up() {
    local st; st=$(cat /sys/class/remoteproc/remoteproc1/state)
    if [ "$st" != "running" ]; then
        echo "CR8 core0 is '$st' -> starting $FW"
        sudo_ "$DIR/board/start-cr8.sh" "$FW" | tail -2
        [ "$(cat /sys/class/remoteproc/remoteproc1/state)" = "running" ] || { echo "CR8 did not come up"; return 1; }
    else
        echo "CR8 core0 running ($(cat /sys/class/remoteproc/remoteproc1/firmware))"
    fi
}
beacon() {  # answer READY to anyone connecting to 127.0.0.1:3335 (the host reads it through the tunnel)
    # OpenBSD nc: options before the address; one connection per nc, so loop.
    while :; do printf 'READY\n' | nc -q 1 -l 127.0.0.1 $BEACON >/dev/null 2>&1 || sleep 1; done
}

case $MODE in
start)
    get_pw
    fw_up || exit 1
    if ocd_running; then echo "OpenOCD already running"; else ocd_start || { echo "OpenOCD failed to start"; exit 1; }; echo "OpenOCD started"; fi
    beacon & BPID=$!
    cleanup() { kill "$BPID" 2>/dev/null; echo; echo "session ending: stopping OpenOCD"; ocd_stop; echo "OpenOCD stopped, CR8 core0: $(cat /sys/class/remoteproc/remoteproc1/state)"; exit 0; }
    trap cleanup HUP INT TERM
    echo "READY  (tunnel: localhost:$PORT -> OpenOCD; close this window or Ctrl-C to end the session)"
    while :; do sleep 3600 & wait $!; done
    ;;
stop)
    get_pw; ocd_stop; echo "OpenOCD stopped, CR8 core0: $(cat /sys/class/remoteproc/remoteproc1/state)"
    ;;
redeploy)
    [ -f "/tmp/$FW" ] || { echo "/tmp/$FW not found (upload it first)"; exit 1; }
    get_pw
    was=0; ocd_running && was=1
    ocd_stop
    sudo_ install -m 644 "/tmp/$FW" "/lib/firmware/$FW"
    sudo_ "$DIR/board/start-cr8.sh" "$FW" | tail -2
    [ "$(cat /sys/class/remoteproc/remoteproc1/state)" = "running" ] || { echo "CR8 did not come up"; exit 1; }
    if [ "$was" = 1 ]; then ocd_start && echo "OpenOCD restarted" || { echo "OpenOCD failed to restart"; exit 1; }; fi
    echo "READY"
    ;;
*) echo "usage: session.sh start|stop|redeploy [fw.elf]"; exit 2;;
esac
