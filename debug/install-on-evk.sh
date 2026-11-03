#!/bin/bash
# Run ON the RZ/V2H EVK (Ubuntu, user with sudo), from a clone of this repo:
#   debug/install-on-evk.sh [openocd-rzv2h-aarch64.tar.gz]
# * installs OpenOCD (prebuilt tarball from the GitHub release if given / found next to the
#   script, otherwise builds it with build-openocd.sh)
# * installs ~/r8ocd/: cr8-dmem.cfg, r8ocd.sh (guarded start), r8dbg.py, board/ helpers
#   (start-cr8.sh, bb.py ...), and the demo firmware into /lib/firmware
# * checks that the board booted with MD_BOOT3=1 (EVK: DSW1-7 ON) and tells you if not
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
DEST=$HOME/r8ocd
TARBALL=${1:-$(ls "$HERE"/openocd-rzv2h-aarch64.tar.gz "$REPO"/openocd-rzv2h-aarch64.tar.gz 2>/dev/null | head -1 || true)}

echo "== OpenOCD"
if command -v openocd >/dev/null && openocd -c 'adapter list' -c exit 2>&1 | grep -qw dmem; then
    echo "   present: $(openocd --version 2>&1 | head -1)"
elif [ -n "$TARBALL" ] && [ -f "$TARBALL" ]; then
    echo "   installing prebuilt $TARBALL into /usr/local"
    sudo apt-get install -y -q libjim0.82t64 >/dev/null 2>&1 || sudo apt-get install -y -q libjim >/dev/null 2>&1 || true
    tmp=$(mktemp -d); tar xzf "$TARBALL" -C "$tmp"
    sudo install -m 755 "$tmp/openocd/bin/openocd" /usr/local/bin/openocd
    sudo mkdir -p /usr/local/share/openocd
    sudo cp -r "$tmp/openocd/share/openocd/scripts" /usr/local/share/openocd/
    rm -rf "$tmp"
    openocd --version 2>&1 | head -1
else
    echo "   no prebuilt tarball: building from source (~10 min)"
    bash "$HERE/build-openocd.sh" /usr/local
fi

echo "== $DEST"
mkdir -p "$DEST/board"
install -m 644 "$HERE/cr8-dmem.cfg" "$DEST/"
install -m 755 "$HERE/r8ocd.sh" "$HERE/r8dbg.py" "$DEST/"
install -m 755 "$REPO"/firmware/tools/board/*.sh "$DEST/board/"
install -m 755 "$REPO"/firmware/tools/board/bb.py "$DEST/board/"
sudo apt-get install -y -q busybox >/dev/null 2>&1 || true

echo "== demo firmware"
if [ -f "$REPO/examples/demo_servo/cr8_demo.elf" ]; then
    sudo install -m 644 "$REPO/examples/demo_servo/cr8_demo.elf" /lib/firmware/cr8_demo.elf
    echo "   /lib/firmware/cr8_demo.elf ($(md5sum /lib/firmware/cr8_demo.elf | cut -c1-8))"
fi

echo "== board checks"
mode=$(sudo busybox devmem 0x10430300 32 2>/dev/null || echo 0)
if [ $(( mode & 0x200 )) -ne 0 ]; then
    echo "   MD_BOOT3=1: debug system enabled"
else
    echo "   !! MD_BOOT3=0 (SYS_LSI_MODE=$mode): the debug system is held in reset."
    echo "      EVK: set DSW1-7 ON and POWER-CYCLE (the pin is latched at power-on)."
fi
for r in /sys/class/remoteproc/remoteproc1; do
    [ -d "$r" ] && echo "   $(cat $r/name): $(cat $r/state)" || echo "   !! no remoteproc1: this kernel has no CR8 remoteproc support"
done
echo
echo "done. Start the gdb server with:  sudo $DEST/r8ocd.sh"
echo "(it refuses to run until the CR8 is started: sudo $DEST/board/start-cr8.sh cr8_demo.elf)"
