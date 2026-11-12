#!/bin/bash
# Robust headless e2studio build.
#   e2s_headless.sh -l LOG [-t SECONDS] -p PROJECT_DIR [-p ...] -b PROJECT[/CONFIG] [-b ...]
# Defences (each one was learned the hard way on the old VM):
#   * a fresh, unique workspace per run (a stale instance holding the workspace lock makes the
#     next build wait forever with no message at all)
#   * every instance we start is recorded in a pidfile and killed on exit/timeout
#   * -no-indexer (the C/C++ indexer is minutes of pure waste)
#   * log-idle detection: if the log stops growing for IDLE seconds while e2studio is still
#     alive, something is waiting on a dialog -> kill and fail loudly (see tools/xwd2png.py in
#     an xwd screenshot of the Xvfb display for how to look at that dialog)
#   * hard timeout as the last resort
# Exit status: 0 only if the log contains "Build Finished" for every -b and no "Build Failed".
set -u
E2STUDIO=${E2STUDIO:-$HOME/rzv-tools/e2studio}
LOG=/tmp/e2s_headless.log; TMO=1500; IDLE=${IDLE:-90}
IMPORTS=(); BUILDS=()
while getopts "l:t:p:b:" o; do
  case $o in
    l) LOG=$OPTARG;; t) TMO=$OPTARG;; p) IMPORTS+=("-import" "$OPTARG");; b) BUILDS+=("-build" "$OPTARG");;
    *) echo "usage: $0 -l LOG [-t SEC] -p DIR... -b PROJECT[/CONFIG]..."; exit 2;;
  esac
done
[ ${#IMPORTS[@]} -gt 0 ] || { echo "no -p project"; exit 2; }
WS=$(mktemp -d /tmp/e2sws.XXXXXX)
PIDF=$WS.pid
: > "$LOG"
cleanup() {
  if [ -f "$PIDF" ]; then
    for p in $(cat "$PIDF"); do kill "$p" 2>/dev/null; done
    sleep 1
    for p in $(cat "$PIDF"); do kill -9 "$p" 2>/dev/null; done
    rm -f "$PIDF"
  fi
  rm -rf "$WS"
}
trap cleanup EXIT
xvfb-run -a -s "-screen 0 1280x1024x24" \
  "$E2STUDIO/eclipse/e2studio" --launcher.suppressErrors -nosplash -consoleLog -data "$WS" \
  -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
  "${IMPORTS[@]}" "${BUILDS[@]}" -no-indexer >> "$LOG" 2>&1 &
BPID=$!
echo "$BPID" > "$PIDF"
LAST=0; STABLE=0; WAITED=0; RC=125
while [ "$WAITED" -lt "$TMO" ]; do
  if ! kill -0 "$BPID" 2>/dev/null; then wait "$BPID"; RC=$?; break; fi
  SZ=$(wc -c < "$LOG" 2>/dev/null || echo 0)
  if [ "$SZ" = "$LAST" ]; then STABLE=$((STABLE + 2)); else STABLE=0; LAST=$SZ; fi
  if [ "$STABLE" -ge "$IDLE" ]; then
    echo "e2s_headless: log idle for ${IDLE}s while e2studio is alive -> stuck (dialog?). killing." | tee -a "$LOG"
    RC=124; break
  fi
  sleep 2; WAITED=$((WAITED + 2))
done
[ "$WAITED" -ge "$TMO" ] && { echo "e2s_headless: hard timeout ${TMO}s" | tee -a "$LOG"; RC=124; }
cleanup; trap - EXIT
# verdict from the log, not from the exit code (e2studio returns 0 on build errors)
NB=$(( ${#BUILDS[@]} / 2 ))
NF=$(grep -c "Build Finished" "$LOG")
# "Clean-only build ... Build Failed" on a fresh tree (nothing to clean) is noise, filter it:
REAL_FAILS=$(awk '/Clean-only build/{c=1;next} /Build Failed/{ if(c){c=0;next} else print } /\*\*\*\* Build of/{c=0}' "$LOG" | wc -l)
echo "e2s_headless: rc=$RC finished=$NF/$NB failed=$REAL_FAILS log=$LOG"
grep -E "error:|undefined reference|Error [0-9]|cannot find|multiple definition" "$LOG" | grep -v "manifest file error" | head -20
[ "$REAL_FAILS" = "0" ] && [ "$NF" -ge "$NB" ] && [ "$RC" != "124" ]
