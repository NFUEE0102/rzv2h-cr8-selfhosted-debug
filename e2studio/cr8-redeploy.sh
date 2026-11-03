#!/bin/bash
# After editing the firmware in e2 studio (Project -> Build Project, Ctrl+B):
#   1. stop OpenOCD on the EVK   (never restart the CR8 while OpenOCD polls it: board hangs)
#   2. post-process the ELF      (zero-size DDR PT_LOADs -> PT_NULL, else remoteproc -22)
#   3. copy it to the EVK as $FW and restart core0 with it
#   4. start OpenOCD again       (the tunnel of cr8-debug.sh keeps running) -> press Debug again
# Disconnect the debug session in e2 studio before clicking this.
set -u
TAG=cr8-redeploy
# shellcheck source=cr8-common.sh
. "$(dirname "$(readlink -f "$0")")/cr8-common.sh"
load_config
ELF=${ELF:-$PROJECT_DIR/Debug/rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo.elf}
TOOLS_DIR=${TOOLS_DIR:-$(cd "$(dirname "$(readlink -f "$0")")/../firmware/tools" && pwd)}

[ -f "$ELF" ] || fail "ELF not found: $ELF (build first: Ctrl+B in e2 studio)"
age=$(( $(date +%s) - $(stat -c %Y "$ELF") ))
say "ELF: $ELF (built $((age/60)) min $((age%60)) s ago)"
ssh_connect

say "1/4 stop OpenOCD on the EVK"
evk_ocd_stop || fail "OpenOCD will not stop"

say "2/4 ELF post-processing"
TMP=$(mktemp -d); cp "$ELF" "$TMP/$FW"
python3 "$TOOLS_DIR/patch-elf-phdr.py" "$TMP/$FW" >/dev/null || fail "patch-elf-phdr failed"
md5sum "$TMP/$FW" | cut -c1-8 | sed 's/^/  md5 /'

say "3/4 deploy and restart core0"
evk_cp "$TMP/$FW" "/tmp/$FW" || fail "scp failed"
evk_sudo "install -m 644 /tmp/$FW /lib/firmware/$FW"
evk_sudo "$OCD_DIR/board/start-cr8.sh $FW" | tail -2 | sed 's/^/  /'
[ "$(evk_state)" = "running" ] || fail "CR8 did not come up"
rm -rf "$TMP"

say "4/4 restart OpenOCD"
evk_ocd_start
tunnel_open
say "done. Back in e2 studio press Debug again."
sleep 3
