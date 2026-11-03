#!/bin/bash
# Host (Linux dev box with e2 studio) setup, run once from a clone of this repo:
#   * asks for the EVK address etc. and writes ~/.config/cr8-debug.conf
#   * installs gdb-multiarch (apt) if missing
#   * builds the demo firmware project if it does not exist yet (headless e2 studio, ~1 min)
#   * drops the e2 studio launch configuration + tunnel script into the project
#   * imports the project into the configured workspace (headless, no GUI needed)
#   * installs the desktop launchers (CR8 Debug / STOP / Redeploy)
# Re-running is safe. Options: --no-build (skip firmware build), --no-desktop.
set -u
TAG=install-host
HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
# shellcheck source=cr8-common.sh
. "$HERE/cr8-common.sh"
NOBUILD=0; NODESK=0
for a in "$@"; do case $a in --no-build) NOBUILD=1;; --no-desktop) NODESK=1;; esac; done

load_config
say "config: $CONF"
say "  EVK=$EVK  FW=$FW"
say "  PROJECT_DIR=$PROJECT_DIR"
say "  E2S=$E2S  WS=$WS"
[ -x "$E2S" ] || fail "e2 studio not found at $E2S (edit $CONF)"

say "1/5 gdb-multiarch"
if command -v gdb-multiarch >/dev/null; then echo "  present"; else
    sudo apt-get install -y -q gdb-multiarch >/dev/null || fail "apt-get install gdb-multiarch failed"
    echo "  installed"
fi

say "2/5 firmware project"
if [ -f "$PROJECT_DIR/.project" ] && [ -f "$PROJECT_DIR/Debug/rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo.elf" ]; then
    echo "  $PROJECT_DIR already built"
elif [ "$NOBUILD" = 1 ]; then
    warn "  project missing and --no-build given; cr8-redeploy will not work until it is built"
else
    variant=$(basename "$PROJECT_DIR")
    echo "  building variant '$variant' with headless e2 studio (patches the FSP packs first)"
    E2STUDIO=$(cd "$(dirname "$E2S")/.." && pwd) bash "$REPO/firmware/tools/build.sh" "$variant" || fail "firmware build failed"
fi

say "3/5 launch configuration into the project"
cp "$HERE/CR8 core0 via OpenOCD dmem.launch" "$PROJECT_DIR/" 2>/dev/null || warn "  project dir missing, launch file not copied"
sed "s#@EVK@#$EVK#g" "$HERE/tunnel-evk.sh" > "$PROJECT_DIR/tunnel-evk.sh" 2>/dev/null && chmod +x "$PROJECT_DIR/tunnel-evk.sh"
cp "$REPO/examples/demo_servo/DEMO.zh-TW.md" "$PROJECT_DIR/" 2>/dev/null || true

say "4/5 e2 studio workspace $WS"
if [ -d "$WS/.metadata/.plugins/org.eclipse.core.resources/.projects/rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo" ]; then
    echo "  project already in the workspace"
else
    mkdir -p "$(dirname "$WS")"
    X=(); command -v xvfb-run >/dev/null && X=(xvfb-run -a -s "-screen 0 1280x1024x24")
    # headless import: the CM33 project must be imported too (the CR8 .cproject references it)
    "${X[@]}" "$E2S" -nosplash -consoleLog -data "$WS" \
        -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
        -import "$REPO/firmware/cm33_demo" -import "$PROJECT_DIR" -no-indexer > "$WS-import.log" 2>&1 \
        && echo "  imported" || warn "  headless import returned non-zero; see $WS-import.log (you can also File -> Import in the GUI)"
fi

say "5/5 desktop launchers"
if [ "$NODESK" = 1 ]; then echo "  skipped"; else
    DESK=${DESKTOP_DIR:-$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")}
    mkdir -p "$DESK"
    for d in CR8-Debug CR8-Debug-Stop CR8-Redeploy; do
        sed "s#@E2STUDIO_DIR@#$HERE#g" "$HERE/$d.desktop" > "$DESK/$d.desktop"
        chmod +x "$DESK/$d.desktop"
        gio set "$DESK/$d.desktop" metadata::trusted true 2>/dev/null || true
        gio set "$DESK/$d.desktop" metadata::xfce-exe-checksum "$(sha256sum "$DESK/$d.desktop" | cut -d' ' -f1)" 2>/dev/null || true
    done
    echo "  $DESK: CR8-Debug / CR8-Debug-Stop / CR8-Redeploy"
fi
say "6/6 deploy the firmware we just built to the EVK"
# The ELF embeds this machine's source paths, so e2 studio finds the sources only for a
# firmware built here. install-on-evk.sh put the prebuilt example on the board; replace it.
if [ "${NODEPLOY:-0}" = 1 ]; then echo "  skipped (NODEPLOY=1)"
elif [ -f "$PROJECT_DIR/Debug/rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo.elf" ]; then
    "$HERE/cr8-redeploy.sh" || warn "  deploy failed (EVK not reachable or debug/install-on-evk.sh not run yet); run cr8-redeploy.sh later"
else
    echo "  no ELF to deploy"
fi
say "done. Click 'CR8 Debug (e2 studio)' on the desktop (EVK must have debug/install-on-evk.sh applied)."
