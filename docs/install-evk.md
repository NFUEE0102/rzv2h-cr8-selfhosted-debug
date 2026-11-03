# EVK side: installing and using the debug stack

## Requirements

* RZ/V2H EVK running Ubuntu with a kernel that has CR8 remoteproc support
  (`/sys/class/remoteproc/remoteproc1/name` = `cr8-core0`). Verified with `6.10.14-arm64-renesas`.
* **DSW1-7 ON** (= `MD_BOOT3` = 1), then a **power cycle**. The pin is latched on the rising
  edge of `PRST_N`; `reboot` is not enough. Check from Linux:
  `sudo busybox devmem 0x10430300 32` → bit 9 set (`0x...3E04`, not `0x...3C04`).
* A user with sudo (stock `ubuntu`/`ubuntu` works) and ~30 MB free in `/usr/local` for
  OpenOCD, or ~500 MB free under `$HOME` if you build it.

## `debug/install-on-evk.sh`

```bash
git clone https://github.com/NFUEE0102/rzv2h-cr8-selfhosted-debug.git
cd rzv2h-cr8-selfhosted-debug
bash debug/install-on-evk.sh [openocd-rzv2h-aarch64.tar.gz]
```

1. **OpenOCD.** If an `openocd` with the `dmem` adapter is already on the `PATH` it is kept.
   Otherwise the prebuilt tarball from the Releases page (passed as argument, or found in
   `debug/` or the repo root) is unpacked into `/usr/local`. It is dynamically linked against
   `libjim.so.0.82`; the script installs `libjim0.82t64` (Ubuntu 24.04 package name). With no
   tarball it builds from source (next section).
2. **`~/r8ocd/`**: `cr8-dmem.cfg`, `r8ocd.sh`, `r8dbg.py`, and `board/` with `start-cr8.sh`,
   `start-cr8-core1.sh`, `restart-r8-pair.sh`, `deploy-cr8.sh`, `bb.py`.
3. **Demo firmware**: `examples/demo_servo/cr8_demo.elf` → `/lib/firmware/cr8_demo.elf`.
4. **Checks**: prints whether `MD_BOOT3` is set and whether `remoteproc1` exists.

## Building OpenOCD from source (`debug/build-openocd.sh`)

Upstream OpenOCD releases up to 0.12.0 do not include the `dmem` adapter; the script builds
master at commit `1f68633` (the one this was verified with) plus
`debug/openocd-isb-before-restart.py`, and installs to `/usr/local` (or the prefix given).

Two things it works around:

* Ubuntu's `libjim-dev` ships no `jimtcl.pc`, and current OpenOCD insists on finding jimtcl
  through pkg-config. The script writes a minimal `~/pc/jimtcl.pc` and points
  `PKG_CONFIG_PATH` at it.
* On these images `/tmp` and `/dev/shm` are emptied when the SSH session that created the
  files logs out. The source tree therefore lives in `~/openocd-src`.

About 10 minutes on the four A55 cores. The tree is left in place; delete it to get the
space back.

## `r8ocd.sh`: the guarded start

`sudo ~/r8ocd/r8ocd.sh` starts OpenOCD with `cr8-dmem.cfg`. Before doing so it checks:

* `CPG_LP_CR8_CTL3` (`0x10420C44`) reads `0x003F3F..` — the CR8 cluster is up and its
  debug APB is open. If not, it refuses: **touching `0x1F8xxxxx` with the cluster down hangs
  the whole board** (power cycle required). Start the firmware first.
* `SYS_LSI_MODE` bit 9 — `MD_BOOT3` is set.

OpenOCD listens on `127.0.0.1:3333` (gdb) and `:4444` (telnet) only; reach it from another
machine through an SSH tunnel.

## Manual use on the board

```bash
sudo ~/r8ocd/board/start-cr8.sh cr8_demo.elf      # load + start core0, checks the black box
sudo ~/r8ocd/r8ocd.sh                              # gdb server (leave running)
# second shell:
gdb -q -ex 'set architecture arm' -ex 'target remote 127.0.0.1:3333' /path/to/firmware.elf
```

Ubuntu's `gdb` on the board (15.1) handles 32-bit Arm targets. Before stopping or
restarting the CR8 (`start-cr8.sh`, `echo stop > /sys/class/remoteproc/remoteproc1/state`,
`restart-r8-pair.sh`), stop OpenOCD: `sudo pkill openocd`.

`sudo ~/r8ocd/r8dbg.py status|pcs N|halt|regs|step N|resume` is the OpenOCD-free
reference; it is useful for a quick PC-sampling profile without stopping anything
(`pcs 20`, then `arm-none-eabi-addr2line -f -e firmware.elf <addr>`).

## Addresses worth knowing

| Address | What |
|---|---|
| `0x439F0000` | Black box of the per-core core0 firmware (`bb.py` decodes it; `+0x44` fault type, `+0x154` tick counter). |
| `0x439FF000` | Demo firmware status words: `+0x00` magic `"DEMO"`, `+0x04` step count, `+0x08` current angle, `+0x0C` pulse width µs, `+0x10` `pwm_apply()` result. `sudo busybox devmem 0x439FF00C 32` shows the pulse without touching the core. |
| `0x1F810000` | CR8 Core0 debug registers (`+0x84` PC sample, `+0x88` DSCR, `+0xFB4` lock status). Only when `CTL3` bit 12 is set. |
| `0x10420C44` | `CPG_LP_CR8_CTL3`. |
| `0x10430300` | `SYS_LSI_MODE`. |

## Uninstall

`sudo pkill openocd; rm -rf ~/r8ocd; sudo rm -f /usr/local/bin/openocd; sudo rm -rf /usr/local/share/openocd; sudo rm -f /lib/firmware/cr8_demo.elf`.
