#!/bin/bash
# Runs one image of the nested-yield experiment on the EVK (as root, on the board).
#   sudo ./run-on-evk.sh <core1 image name in /lib/firmware> [seconds]
# Restarts the CR8 pair with the given core1 image, floods core1 with rpmsg echoes and prints one
# status line per echo run (the w<N> words are described in exp_nested_yield.c). Stops early when
# the black box reports a fault or two runs in a row fail.
# env: CORE0 (core0 image, default cr8_demo.elf), TOOLS (dir with restart-r8-pair.sh and bb.py),
#      BENCH (dir with the core1 echo client r8_bench_c1), N (echoes per run, default 20000)
set -u
FW1=${1:?usage: run-on-evk.sh <core1.elf> [seconds]}
DUR=${2:-300}
UHOME=$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)
CORE0=${CORE0:-cr8_demo.elf}
TOOLS=${TOOLS:-$UHOME/cr8-fw-tools}
BENCH=${BENCH:-$UHOME/r8_bench_c1}
N=${N:-20000}
CLIENT=${CLIENT:-./r8_bench_c1}     # the echo client binary, run from $BENCH
BB=0x441F0000                      # core1 black box
RP=/sys/class/remoteproc/remoteproc2
rd() { echo $(($(busybox devmem $((BB + $1)) 32))); }
rdx() { busybox devmem $((BB + $1)) 32; }
w() { rd $((0x800 + 4 * $1)); }
wx() { rdx $((0x800 + 4 * $1)); }

status() {
  printf "t=%-4d fault=%s tick=%d echoes=%d nested_irq=%d | nested_yield=%d outer_flag_set=%d outer_flag_clear=%d ids=%s rpr_inner=%s task=%s sched_not_running=%d | woke_during=%d woke_after=%d task_in_isr=%d rpr=%s ticks_bad=%s ticks_norm=%s | cnt=%s/%s/%s cmp=%s work=%d/%d | rproc=%s %s\n" \
    "$SECONDS" "$(rdx 0x44)" "$(rd 0x154)" "$(rd 0x18)" "$(rd 0x240)" \
    "$(w 1)" "$(w 2)" "$(w 3)" "$(wx 4)" "$(wx 5)" "$(wx 6)" "$(w 7)" \
    "$(w 8)" "$(w 9)" "$(w 10)" "$(wx 11)" "$(wx 12)" "$(wx 13)" \
    "$(wx 14)" "$(wx 15)" "$(wx 16)" "$(wx 17)" "$(w 18)" "$(w 19)" "$(cat $RP/state)" "$1"
}

# the experiment block lives in plain DDR that survives a CR8 restart: clear it first
for i in $(seq 0 19); do busybox devmem $((BB + 0x800 + 4 * i)) 32 0; done
sh "$TOOLS/restart-r8-pair.sh" "$CORE0" "$FW1" 2>&1 | grep -v "^==" | head -n 4
sleep 3
SECONDS=0
status "start"
bad=0
cd "$BENCH" || exit 1
while [ "$SECONDS" -lt "$DUR" ]; do
  out=$(timeout ${RUN_TIMEOUT:-60} "$CLIENT" "$N" 2>&1); rc=$?
  sum=$(echo "$out" | grep -o "[0-9]*/[0-9]* ok, [0-9]* errors" | tr "\n" ";")
  if [ "$rc" -eq 0 ] && echo "$out" | grep -q "ok, 0 errors" && ! echo "$out" | grep -q "ok, [1-9][0-9]* errors"; then
    res="run=ok"; bad=0
  else
    res="run=FAILED(rc=$rc)"; bad=$((bad + 1))
  fi
  status "$res [$sum]"
  [ "$(rdx 0x44)" != "0x00000000" ] && { echo "fault recorded: stopping"; break; }
  [ "$bad" -ge 2 ] && { echo "two failed runs in a row: stopping"; break; }
done
echo "$out" | grep -i "percentiles\|outliers\|throughput" | head -n 3
echo "---- black box"
python3 "$TOOLS/bb.py" --addr $BB 2>&1 | head -n 60
