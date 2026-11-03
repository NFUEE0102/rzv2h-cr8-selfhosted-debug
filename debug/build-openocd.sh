#!/bin/bash
# Build OpenOCD with the dmem adapter + our ISB patch, natively on the RZ/V2H (Ubuntu 24.04).
# ~10 min on the four A55s, needs ~500 MB of disk during the build.
#   debug/build-openocd.sh [prefix]      default prefix /usr/local  (needs sudo for install)
# Pitfalls handled: Ubuntu's libjim-dev ships no jimtcl.pc (configure insists on pkg-config);
# /tmp and /dev/shm are wiped at SSH logout on these images, so build under $HOME.
set -eu
PREFIX=${1:-/usr/local}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$HOME/openocd-src
REV=${OPENOCD_REV:-1f68633}          # upstream commit this was verified with (2026-11-01)

sudo apt-get install -y -q git make autoconf automake libtool pkg-config gcc libjim-dev >/dev/null

mkdir -p "$HOME/pc"
cat > "$HOME/pc/jimtcl.pc" <<EOF
prefix=/usr
libdir=/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)
includedir=/usr/include
Name: jimtcl
Description: Jim Tcl (Ubuntu libjim-dev ships no .pc)
Version: $(dpkg-query -W -f='${Version}' libjim-dev | cut -d- -f1)
Libs: -L\${libdir} -ljim
Cflags: -I\${includedir}
EOF
export PKG_CONFIG_PATH=$HOME/pc

if [ ! -d "$SRC" ]; then
    git clone --depth 50 https://github.com/openocd-org/openocd.git "$SRC"
fi
cd "$SRC"
git checkout -q "$REV" 2>/dev/null || { git fetch --depth 200; git checkout -q "$REV"; }
python3 "$HERE/openocd-isb-before-restart.py" .
./bootstrap nosubmodule >/dev/null
./configure --prefix="$PREFIX" --enable-dmem --disable-werror --disable-doxygen-html --disable-doxygen-pdf > configure.log
grep -q "BUILD_DMEM 1" config.h || { echo "dmem adapter not enabled, see configure.log"; exit 1; }
make -j"$(nproc)" > make.log 2>&1 || { tail -30 make.log; exit 1; }
sudo make install > /dev/null
echo "installed: $("$PREFIX/bin/openocd" --version 2>&1 | head -1)"
echo "source tree left in $SRC (rm -rf it to get ~500 MB back)"
