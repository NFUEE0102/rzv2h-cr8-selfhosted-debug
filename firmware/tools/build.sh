#!/bin/bash
# Build one CR8 firmware variant from base/ with the headless e2studio, then post-process the ELF.
#   build.sh <variant> [--keep] [--no-build]
# variants:
#   core0-pwm         core0, per-core layout (EVK): rpmsg echo + PWM control + black box   [cr8_pwm_demo]
#   core0-pwm-shared  same firmware on the legacy shared layout (RDK device tree)          [cr8_demo_patched lineage]
#   core0-pwm-plane   core0-pwm with only 4 outputs on EVK Pmod CN2-7..10 (P74/P75/PA6/PA4 = GPT4A/4B/7A/6A),
#                     pulse clamp 1000..2000 us: fixed-wing bench, 1 ESC + 3 servos           [cr8_pwm_plane]
#   core0-demo        core0-pwm-plane + src/demo_servo.c: angle sweep on CN2-8 with a planted 16-bit
#                     overflow bug, built -O0, for the single-step / fix-it debugger demo   [cr8_demo]
#   core1-echo        core1, per-core layout: rpmsg echo + black box
#   core1-uart        core1-echo + RSCI5 UART demo channel (P72/P73, UARC/UARS protocol)     [cr8_core1_demo]
#   exp-nested-yield  core1-echo + the nested-interrupt context-switch probe (experiments/nested-yield)
#   exp-normal-app    same probe in an ordinary application workload (100 Hz control task + housekeeping)
# env: E2STUDIO (~/rzv-tools/e2studio) CM33_PROJECT (<firmware>/cm33_demo, imported so the interlock .sbd
#      reference resolves) TC (GNU Arm toolchain bin dir; default = the one bundled with e2studio)
# Output: out/<variant>.elf (+ .map, .md5, build log) ; work tree in build/<variant>/
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
CR8FW=$(cd "$HERE/.." && pwd)
V=${1:?variant}; shift
NOBUILD=0
for a in "$@"; do case $a in --no-build) NOBUILD=1;; esac; done
E2STUDIO=${E2STUDIO:-$HOME/rzv-tools/e2studio}
CM33_PROJECT=${CM33_PROJECT:-$CR8FW/cm33_demo}
# GNU Arm Embedded toolchain: prefer the copy e2studio installs, else a system one
if [ -z "${TC:-}" ]; then
  TC=$(ls -d "$E2STUDIO"/toolchains/gcc_arm/*/bin /opt/toolchains/gcc_arm/*/*/bin 2>/dev/null | head -1)
  [ -n "$TC" ] || TC=$(dirname "$(command -v arm-none-eabi-gcc 2>/dev/null || echo /usr/bin/arm-none-eabi-gcc)")
fi
B=$CR8FW/build/$V
OUT=$CR8FW/out
PROJ=rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo
CM33=rzv2h_rdk_cm33_rpmsg_linux_rtos_demo
export PATH="$TC:$PATH"
mkdir -p "$OUT"
echo "== [$V] assemble work tree"
rm -rf "$B"; mkdir -p "$CR8FW/build"; cp -r "$CR8FW/base" "$B"
CORE=0
case $V in
  core0-pwm) ;;
  core0-pwm-shared) python3 "$CR8FW/variants/layout_shared.py" "$B" || exit 1;;
  core0-pwm-plane) python3 "$CR8FW/variants/core0_pwm_plane.py" "$B" || exit 1;;   # EVK CN2-7..10: ESC + 3 servos
  core0-demo) python3 "$CR8FW/variants/core0_pwm_plane.py" "$B" || exit 1              # single-step/fix-it demo on CN2-8
             python3 "$CR8FW/variants/core0_demo.py" "$B" || exit 1;;
  core1-echo) CORE=1; python3 "$CR8FW/variants/core1_echo.py" "$B" || exit 1;;
  core1-uart) CORE=1; python3 "$CR8FW/variants/core1_echo.py" "$B" || exit 1
              python3 "$CR8FW/variants/core1_uart.py" "$B" || exit 1;;
  exp-nested-yield) CORE=1; python3 "$CR8FW/variants/core1_echo.py" "$B" || exit 1   # experiments/nested-yield
              python3 "$CR8FW/experiments/nested-yield/apply.py" "$B" || exit 1;;
  exp-normal-app) CORE=1; python3 "$CR8FW/variants/core1_echo.py" "$B" || exit 1     # experiments/nested-yield
              python3 "$CR8FW/experiments/nested-yield/apply.py" "$B" --workload 2 || exit 1;;
  *) echo "unknown variant $V"; exit 2;;
esac
[ "$NOBUILD" = 1 ] && { echo "work tree ready: $B"; exit 0; }

echo "== [$V] packs"
# the generator reads the per-user pack cache (~/.eclipse/com.renesas.platform_*), which only a GUI
# start fills: seed it from the install first, then make sure every copy carries our patches
python3 "$HERE/seed_pack_cache.py" --e2studio "$E2STUDIO" || { echo "pack cache seeding failed"; exit 1; }
python3 "$HERE/patch_packs.py" --e2studio "$E2STUDIO" --check | grep -v "^  ok" || true
python3 "$HERE/patch_packs.py" --e2studio "$E2STUDIO" > /dev/null || { echo "pack patching failed"; exit 1; }

echo "== [$V] headless e2studio build"
IMP=(-p "$B"); BLD=(-b "$PROJ/Debug")
if [ -d "$CM33_PROJECT" ]; then IMP=(-p "$CM33_PROJECT" -p "$B"); BLD=(-b "$CM33/Debug" -b "$PROJ/Debug"); fi
E2STUDIO=$E2STUDIO bash "$HERE/e2s_headless.sh" -l "$OUT/$V.build.log" "${IMP[@]}" "${BLD[@]}" || { echo "BUILD FAILED ($OUT/$V.build.log)"; exit 1; }
ELF=$B/Debug/$PROJ.elf
[ -f "$ELF" ] || { echo "no ELF produced"; exit 1; }

echo "== [$V] regeneration + pack-patch check"
python3 "$HERE/check_regen.py" "$B" || exit 1

echo "== [$V] ELF post-processing"
python3 "$HERE/patch-elf-phdr.py" "$ELF" || exit 1
if [ "$CORE" = 1 ]; then
  # .wait_data_other_core sits in core0's SRAM tail: outside this core's rproc window (-22) and,
  # if it loaded, it would clear core0's init-arbitration word
  python3 "$HERE/null_phdr_at.py" "$ELF" 0x081BFFFC || exit 1
elif [ "${NULL_CORE0_WAIT:-0}" = 1 ]; then
  python3 "$HERE/null_phdr_at.py" "$ELF" 0x081FFFFC || exit 1
fi
cp "$ELF" "$OUT/$V.elf"; cp "$B/Debug/$PROJ.map" "$OUT/$V.map" 2>/dev/null
md5sum "$OUT/$V.elf" | tee "$OUT/$V.md5"
"$TC/arm-none-eabi-size" "$OUT/$V.elf" | tail -1
"$TC/arm-none-eabi-readelf" -l "$OUT/$V.elf" | grep -E "^\s+(LOAD|NULL)" | awk '{printf "  %s %s filesz %s\n", $1, $3, $5}'
echo "== [$V] done -> $OUT/$V.elf"
