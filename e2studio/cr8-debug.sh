#!/bin/bash
# One click from the desktop:  EVK firmware running? -> OpenOCD on the EVK -> SSH tunnel
# :3333 -> e2 studio.  Closing e2 studio (or Ctrl-C) closes the tunnel and stops OpenOCD, so
# nothing keeps polling the CR8 debug registers (that would hang the board the moment the CR8
# is stopped or restarted).
#
#   cr8-debug.sh            full flow (desktop launcher)
#   cr8-debug.sh --no-ide   bring everything up, verify, tear down (self-test)
#   cr8-debug.sh --stop     only tear down (tunnel + OpenOCD on the EVK)
set -u
TAG=cr8-debug; export TAG   # used by say/warn/fail in cr8-common.sh
# shellcheck source=cr8-common.sh
. "$(dirname "$(readlink -f "$0")")/cr8-common.sh"
load_config

teardown() {
    say "tear-down: close tunnel, stop OpenOCD on the EVK"
    tunnel_close
    if ssh "${SSH_OPTS[@]}" -O check "$EVK" 2>/dev/null; then
        evk_ocd_stop && echo "  OpenOCD stopped" || echo "  OpenOCD still running (!)"
        echo "  CR8 core0: $(evk_state)"
    fi
    ssh_close
}

if [ "${1:-}" = "--stop" ]; then ssh_connect; teardown; exit 0; fi
trap teardown EXIT INT TERM

say "1/3 EVK ($EVK): firmware + OpenOCD"
ssh_connect
state=$(evk_state)
if [ "$state" != "running" ]; then
    say "  CR8 core0 is '$state' -> starting $FW"
    evk_sudo "$OCD_DIR/board/start-cr8.sh $FW" | tail -2 | sed 's/^/  /'
    [ "$(evk_state)" = "running" ] || fail "CR8 did not come up"
else
    say "  CR8 core0 running (firmware: $(evk cat /sys/class/remoteproc/remoteproc1/firmware))"
fi
if evk_ocd_running; then say "  OpenOCD already running"; else evk_ocd_start; say "  OpenOCD started (Examination succeed)"; fi

say "2/3 tunnel localhost:$PORT -> EVK:$PORT"
tunnel_open
say "  tunnel OK"

if [ "${1:-}" = "--no-ide" ]; then say "3/3 (--no-ide) skipped e2 studio; self-test passed"; exit 0; fi

say "3/3 e2 studio, workspace $WS"
say "  Run -> Debug Configurations -> GDB Hardware Debugging -> 'CR8 core0 via OpenOCD dmem'"
say "  leave with Disconnect; closing e2 studio tears everything down"
mkdir -p "$(dirname "$WS")"
"$E2S" -data "$WS" > "$WS-e2s.log" 2>&1
