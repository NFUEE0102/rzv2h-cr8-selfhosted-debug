#!/bin/sh
# Start OpenOCD as a gdb server for the CR8 (see cr8-dmem.cfg).
# Refuses to run unless the CR8 debug APB is up: with CPG_LP_CR8_CTL3 bit12
# clear, the first access to 0x1F8xxxxx hangs the whole board.
set -e
# $HOME is /root under sudo, so never derive paths from it. install-on-evk.sh puts the
# dmem-enabled build in /usr/local/bin; OCD= overrides.
OCD=${OCD:-$(command -v openocd || true)}
[ -n "$OCD" ] && [ -x "$OCD" ] || OCD=/home/ubuntu/openocd/bin/openocd
[ -x "$OCD" ] || { echo "openocd not found (run debug/install-on-evk.sh)" >&2; exit 1; }
CFG=${CFG:-$(dirname "$0")/cr8-dmem.cfg}

ctl3=$(busybox devmem 0x10420C44 32)
case $ctl3 in
  0x003F3F*) ;;
  *) echo "CPG_LP_CR8_CTL3=$ctl3: CR8 debug APB not ready (start the CR8 first). Refusing." >&2
     exit 1 ;;
esac
mode=$(busybox devmem 0x10430300 32)
if [ $(( mode & 0x200 )) -eq 0 ]; then
  echo "SYS_LSI_MODE=$mode: MD_BOOT3=0, debug system is in reset (EVK: DSW1-7 ON + power cycle)." >&2
  exit 1
fi
exec "$OCD" -f "$CFG" "$@"
