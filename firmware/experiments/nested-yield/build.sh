#!/bin/bash
# Builds the two firmware images of the nested-yield experiment (Linux host):
#   build.sh [exp-nested-yield|exp-normal-app]
#   out/exp-nested-yield-guard.elf    FSP 4.3.0 + our pack patches (interrupt-nesting count in IRQ_Handler)
#   out/exp-nested-yield-vendor.elf   same sources, but portASM.asm is the v4.3.0 file from the pack, byte for byte
# The second one is made by putting the pristine file from the pack back into the generated tree
# and re-running the generated makefile (the FSP generator is not involved, so the file stays).
# env: E2STUDIO, TC as for tools/build.sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
FW=$(cd "$HERE/../.." && pwd)
E2STUDIO=${E2STUDIO:-$HOME/rzv-tools/e2studio}
if [ -z "${TC:-}" ]; then
  TC=$(ls -d "$E2STUDIO"/toolchains/gcc_arm/*/bin 2>/dev/null | head -1)
fi
V=${1:-exp-nested-yield}          # or exp-normal-app
PROJ=rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo
B=$FW/build/$V
ASM_REL=rz/fsp/src/rm_freertos_port/cr8/portASM.asm
PACK=$E2STUDIO/internal/projectgen/rz_fsp/packs/Renesas.RZV.4.3.0.pack

E2STUDIO=$E2STUDIO TC=$TC bash "$FW/tools/build.sh" $V
cp "$FW/out/$V.elf" "$FW/out/$V-guard.elf"
grep -q ulPortInterruptNesting "$B/$ASM_REL" || { echo "guard build has no nesting count?"; exit 1; }

echo "== [$V] vendor handler: pristine portASM.asm from $(basename "$PACK").orig"
[ -f "$PACK.orig" ] || { echo "no $PACK.orig (patch_packs.py keeps the vendor pack under that name)"; exit 1; }
unzip -p "$PACK.orig" "$ASM_REL" > "$B/$ASM_REL"
if grep -q ulPortInterruptNesting "$B/$ASM_REL"; then echo "pack .orig is not pristine"; exit 1; fi
sha256sum "$B/$ASM_REL"
PATH="$TC:$PATH" make -C "$B/Debug" "$PROJ.elf" > "$FW/out/$V-vendor.build.log" 2>&1 || { echo "make failed ($FW/out/$V-vendor.build.log)"; exit 1; }
ELF=$B/Debug/$PROJ.elf
python3 "$FW/tools/patch-elf-phdr.py" "$ELF" > /dev/null
python3 "$FW/tools/null_phdr_at.py" "$ELF" 0x081BFFFC > /dev/null
cp "$ELF" "$FW/out/$V-vendor.elf"
md5sum "$FW/out/$V-guard.elf" "$FW/out/$V-vendor.elf"
for e in guard vendor; do
  printf "%s: instructions in IRQ_Handler that load ulPortInterruptNesting: " $e
  "$TC/arm-none-eabi-objdump" -d "$FW/out/$V-$e.elf" | awk '/<IRQ_Handler>:/{f=1} /<switch_before_exit>:/{f=0} f' | grep -c ulPortInterruptNesting || true
done
