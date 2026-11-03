#!/bin/bash
# Start the plane web remote on the EVK (run as root).  Reloads the core0 firmware first so the
# rpmsg channel is freshly announced (pwmd reconnect after a previous client is unreliable,
# see a55-r8-demo-toolkit), then runs server.py in the background.
#   sudo bash start.sh [port]
set -u
PORT=${1:-8090}
HERE=$(cd "$(dirname "$0")" && pwd)
LOG=/var/log/plane_remote.log
pkill -f "[s]erver.py --port" 2>/dev/null      # any earlier instance, however it was launched
pkill -f "[i]bus_sim.py" 2>/dev/null
pkill -f "[r]8_bench pwmd" 2>/dev/null
sleep 0.5
bash /home/ubuntu/cr8-fw-tools/start-cr8.sh cr8_pwm_plane.elf || exit 1
sleep 1
nohup python3 "$HERE/server.py" --port "$PORT" >> "$LOG" 2>&1 &
sleep 2.5
if curl -fs "http://127.0.0.1:$PORT/state" > /dev/null; then
  echo "plane_remote up: http://$(hostname -I | awk '{print $1}'):$PORT   (log $LOG)"
else
  echo "plane_remote failed, see $LOG"; tail -5 "$LOG"; exit 1
fi
