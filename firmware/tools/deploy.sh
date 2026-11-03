#!/bin/bash
# Install a CR8 firmware on a board and (re)start the core with the required pre-start sequence.
#   deploy.sh <host> <elf> --core 0|1 [--name NAME.elf] [--user ubuntu] [--pw SUDO_PASSWORD]
#                          [--pair FW0.elf FW1.elf] [--no-start]
# Rules baked in (devkit docs/03 + docs/10):
#   * the core must really be offline before the firmware name is written (EBUSY otherwise and
#     the OLD image keeps running while sysfs says "running")
#   * stale MHU doorbell + both virtio status bytes are cleared before start (both layouts)
#   * a core that has run once must NOT be restarted alone while the other R8 is running
#     (no per-core reset: it resumes at the old PC inside the new image) -> use --pair, which
#     stops both and starts core0 then core1
#   * the black box is read back after start (fault_type must be 0 / 0xFFFFFFFF on cold DDR)
# The board-side helpers (tools/board/*, from the public devkit) are copied to ~/cr8-fw-tools.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
HOST=${1:?host}; ELF=${2:?elf}; shift 2
CORE=0; NAME=""; USER_=ubuntu; PW=""; PAIR=(); START=1
while [ $# -gt 0 ]; do
  case $1 in
    --core) CORE=$2; shift 2;; --name) NAME=$2; shift 2;; --user) USER_=$2; shift 2;;
    --pw) PW=$2; shift 2;; --pair) PAIR=("$2" "$3"); shift 3;; --no-start) START=0; shift;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[ -f "$ELF" ] || { echo "no such file $ELF"; exit 1; }
[ -n "$NAME" ] || NAME=$(basename "$ELF")
if [ -n "$PW" ]; then SUDO="echo $PW | sudo -S -p ''"; else SUDO="sudo"; fi
T=cr8-fw-tools          # relative to the board user's home (scp does not expand \$HOME)
echo "== copy $ELF -> $HOST:~/$NAME  (+ board tools)"
scp -q "$ELF" "$USER_@$HOST:$NAME" || exit 1
ssh "$USER_@$HOST" "mkdir -p $T" && scp -q "$HERE"/board/* "$USER_@$HOST:$T/" || exit 1
ssh "$USER_@$HOST" "chmod +x $T/*.sh; $SUDO cp $NAME /lib/firmware/$NAME && $SUDO chmod 644 /lib/firmware/$NAME && echo \"  installed /lib/firmware/$NAME (\$(md5sum /lib/firmware/$NAME | cut -c1-32))\"" || exit 1
[ "$START" = 1 ] || exit 0
if [ ${#PAIR[@]} -eq 2 ]; then
  echo "== pair restart: core0=${PAIR[0]} core1=${PAIR[1]}"
  ssh "$USER_@$HOST" "$SUDO sh $T/restart-r8-pair.sh ${PAIR[0]} ${PAIR[1]}"
else
  echo "== start core$CORE with $NAME"
  if [ "$CORE" = 1 ]; then S=start-cr8-core1.sh; else S=start-cr8.sh; fi
  ssh "$USER_@$HOST" "$SUDO bash $T/$S $NAME; echo \"  state: core0=\$(cat /sys/class/remoteproc/remoteproc1/state) core1=\$(cat /sys/class/remoteproc/remoteproc2/state 2>/dev/null)\"; $SUDO python3 $T/bb.py --all 2>/dev/null | head -8"
fi
