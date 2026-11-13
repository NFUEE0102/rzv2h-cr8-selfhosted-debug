# rzv2h-cr8-selfhosted-debug

Source-level debugging of the Renesas RZ/V2H Cortex-R8 (CR8) from the Cortex-A55 Linux
running on the same chip. No J-Link, no cable: OpenOCD runs on the A55, reaches the CR8
debug registers through `/dev/mem`, and e² studio talks to it exactly as it would talk to a
J-Link gdb server. Halt, registers, single step, hardware breakpoints, memory, all from the
board itself — also when the board is sealed inside an airframe.

```
 Linux host (e² studio)                      RZ/V2H EVK
 ┌──────────────────────┐   ssh -L 3333   ┌──────────────────────────────────────────┐
 │ e² studio            │ ──────────────▶ │ A55 Linux                                │
 │  GDB Hardware Debug  │  localhost:3333 │   OpenOCD (dmem adapter) ──/dev/mem──▶   │
 │  gdb-multiarch       │                 │   CR8 Core0 debug APB  0x1F810000        │
 └──────────────────────┘                 │   CR8 Core0  ◀── halt / step / bp        │
                                          └──────────────────────────────────────────┘
```

The repository is complete: firmware sources and build system, the debug tooling for the
board, the e² studio integration for the host (Linux and Windows), and a demo firmware with a
planted bug to walk through. Both CR8 cores can be debugged at the same time.

**Current release: v1.1.0** (e² studio 2026-10 + RZ FSP 4.3.0; Ubuntu and Windows hosts, both
cores, Windows UI in zh-TW/en/ja) -- see the
[Releases](https://github.com/NFUEE0102/rzv2h-cr8-selfhosted-debug/releases) page for the
prebuilt OpenOCD, the demo firmware and `CR8DebugApp.exe`. The firmware build moved to RZ FSP
4.3.0 in this release (see [FSP 4.3.0](#fsp-430-done-2026-11-12)); v1.0.1 is the last one for
e² studio 2025-01 + RZ/V FSP 3.1.0, and its firmware images still run.

## Prerequisites

| Side | Requirement |
|---|---|
| RZ/V2H EVK | Ubuntu with the 6.10 kernel that has CR8 remoteproc support (`/sys/class/remoteproc/remoteproc1` = `cr8-core0`). **DSW1-7 ON** (MD_BOOT3 = 1), then **power-cycle** — the pin is latched at power-on reset. A user with sudo (the stock `ubuntu` account works). |
| Linux host | e² studio 2026-10 with the RZ FSP 4.3.0 pack and its bundled GNU Arm 13.3 toolchain (for building the firmware; debugging a prebuilt ELF needs only e² studio), `python3`, `ssh`, `gdb-multiarch` (installed by the host script). Tested on Ubuntu 24.04 with an XFCE desktop (all six firmware variants build headless there with e² studio 2026-10 + RZ FSP 4.3.0; the e² studio GUI debug session was last exercised with 2025-01). |
| Windows host | e² studio 2026-10 + RZ FSP 4.3.0 under `C:\Renesas` (the installer `setup_rzfsp_v4_3_0_e2s_v2026-10.exe` from the [rz-fsp v4.3.0 release](https://github.com/renesas/rz-fsp/releases/tag/v4.3.0)), Python 3 from python.org (`py` launcher), `paramiko` (installed by the host script). No SSH key, no `ssh.exe` needed. See [docs/windows-host.md](docs/windows-host.md). |
| Network | Host reaches the EVK over SSH with a password. No keys required. |

## Quick start (three steps)

1. **On the EVK**
   ```bash
   git clone https://github.com/NFUEE0102/rzv2h-cr8-selfhosted-debug.git
   cd rzv2h-cr8-selfhosted-debug
   # optional: download openocd-rzv2h-aarch64.tar.gz from the Releases page into debug/
   bash debug/install-on-evk.sh
   ```
   Installs OpenOCD (prebuilt tarball if present, otherwise builds it, ~10 min), `~/r8ocd/`
   (config, guarded start script, `r8dbg.py`, board helpers) and `/lib/firmware/cr8_demo.elf`.
   It ends by telling you whether MD_BOOT3 is set.

2. **On the host**
   ```bash
   git clone https://github.com/NFUEE0102/rzv2h-cr8-selfhosted-debug.git
   cd rzv2h-cr8-selfhosted-debug
   bash e2studio/install-host.sh
   ```
   Asks for the EVK IP, user and password (password stored only if you say so), installs
   `gdb-multiarch`, builds the demo firmware project with headless e² studio, imports it into
   a workspace, puts three launchers on the desktop and deploys the freshly built firmware to
   the EVK (so the sources resolve in e² studio; the prebuilt ELF from step 1 is replaced).

3. **Click `CR8 Debug (e2 studio)`** on the desktop. A terminal shows three status lines
   (EVK firmware + OpenOCD, tunnel, e² studio), then e² studio opens. In e² studio:
   Run → Debug Configurations → GDB Hardware Debugging → **CR8 core0 via OpenOCD dmem** →
   Debug. The core halts; set breakpoints, step, inspect.

The first SSH connection of a session asks for the password once; every later command of
that session reuses the connection (OpenSSH ControlMaster), so no `sshpass` and no keys.

**Windows host instead of Linux:** unzip, download `CR8DebugApp.exe` from the Releases page
into that folder and double-click it (or `CR8-Debug-App.cmd`; needs Python 3). To build the
demo firmware on the PC too, run `windows-setup.cmd` once (headless e² studio build, Desktop
shortcuts).
One window asks for the EVK IP, user and password, logs in, installs the EVK side itself if
step 1 was skipped, starts firmware + OpenOCD, opens the gdb ports through its own SSH
connection and launches e² studio. Both CR8 cores can be debugged at the same time (two
launch configurations, ports 3333 and 3334). UI in Traditional Chinese, English and
Japanese. Details:
[docs/windows-host.md](docs/windows-host.md).

## Desktop buttons

| Button | What it does |
|---|---|
| `CR8 Debug (e2 studio)` | Starts the firmware if the core is offline, starts OpenOCD on the EVK, opens the tunnel, launches e² studio. Closing e² studio tears all of it down. |
| `CR8 Debug STOP` | Manual tear-down: tunnel + OpenOCD. Press it before anything that stops or restarts the CR8. |
| `CR8 Redeploy` | After editing and building in e² studio (Project → Build Project, Ctrl+B): stops OpenOCD, post-processes the ELF, copies it to the EVK, restarts core0, restarts OpenOCD. Then press Debug again. |

Configuration lives in `~/.config/cr8-debug.conf` (EVK address, user, optional password,
firmware name, project, workspace). Delete it to be asked again.

## Three rules

1. **DSW1-7 must be ON at power-on.** Otherwise the CoreSight system is held in reset and
   nothing below works. `install-on-evk.sh` and `r8ocd.sh` check this.
2. **Never access `0x1F8xxxxx` before the CR8 cluster is up.** Until remoteproc has started
   the CR8 (`CPG_LP_CR8_CTL3` bit 12 = 1) the CR8 debug APB is isolated and the first read
   hangs the system bus; the whole board needs a power cycle. `r8ocd.sh` refuses to start
   until the gate is open.
3. **Never stop or restart the CR8 while OpenOCD is running.** OpenOCD polls the debug
   registers; once the cluster goes down that poll hangs the bus (same outcome). `CR8 Debug
   STOP` first, or use `CR8 Redeploy`, which does it in the right order.
4. **Stop OpenOCD gracefully, never with a core left halted.** A core that stays halted after
   its debugger is killed, and is then restarted by the next OpenOCD from stale state, took an
   undefined-instruction exception on both CR8 cores once. The scripts resume every target
   and `shutdown` over the telnet port before falling back to `pkill`; do the same by hand.

While the core is halted the GPT PWM outputs stay at their last duty cycle, the firmware
tick stops and rpmsg clients on Linux time out. Flight hardware: props off.

## Repository layout

| Path | Contents |
|---|---|
| `firmware/` | CR8 firmware: e² studio base project, variant transforms, FSP patches, headless build and deploy tools. See [docs/build-firmware.md](docs/build-firmware.md). |
| `debug/` | Board-side debug stack: `cr8-dmem.cfg` (OpenOCD), `r8ocd.sh` (guarded start), `r8dbg.py` (pure-Python halt/step reference), OpenOCD patch and build script, `install-on-evk.sh`. |
| `e2studio/` | Host side: `install-host.sh`, `cr8-debug.sh`, `cr8-redeploy.sh`, shared `cr8-common.sh`, the `.launch` file, desktop launcher templates; `windows/` holds the Windows app (`cr8_debug_app.py`), `install-host.ps1` and the `ssh.exe`-based launchers. |
| `examples/demo_servo/` | Demo firmware source, prebuilt `cr8_demo.elf`, English walkthrough and Traditional Chinese presenter script. |
| `docs/` | [How it works and what we had to discover](docs/self-hosted-debug.md), [EVK install details](docs/install-evk.md), [firmware build](docs/build-firmware.md), [Windows host](docs/windows-host.md). |

## Status

Password-only hosts (no SSH key to the EVK) are verified: a fresh user with an empty
`EVK_PASS` is asked exactly once by `ssh` for the login password and once by the script for
the EVK sudo password per launch; every later ssh/scp in that run rides on the same
connection (OpenSSH ControlMaster). Each launcher run closes the connection when it ends, so
the next run asks again unless the password is stored in the config.

Verified on an RZ/V2H EVK (Ubuntu, kernel 6.10.14) with e² studio 2025-01 on Ubuntu 24.04:
attach, registers, `stepi`/Step Over, memory, hardware breakpoints with conditions, Disconnect
and Terminate both leave the core running, redeploy loop. CR8 core1 is verified too (second
target, gdb port 3334; halting one core leaves the other running). The CM33 cannot be reached
this way: its debug registers live on its private bus behind the DAP's AHB-AP and are not on
the system bus (the CST ROM table lists CA55 and CR8 only).

**RZ FSP 4.3.0 build (2026-11-13, Windows 10, e² studio 2026-10, `firmware/tools/build.ps1`):**
all six variants build headless; on the EVK `core0-demo` + `core1-uart` boot as a pair, tick at
1 kHz (ISR jitter 1.0 µs peak to peak) and echo at 10,088 round trips/s, 98.6 µs average (the
3.1.0 build: 10,145 / 98.0 µs, same board, same client). Repeated host connections, the PWM and
jitter commands and the core1 channel work. The debug path was re-run through the app's own
classes (password login, OpenOCD start, in-process tunnel) with the 2026-10
`arm-none-eabi-gdb.exe`: hardware breakpoint in `demo_servo_step()`, Step Over, the conditional
breakpoint `deg >= 70` (stops with `pulse_us = 1049`, the planted overflow), a breakpoint on
core1 while core0 keeps ticking, graceful stop, redeploy of the pair. Nested-interrupt soak (MHU
doorbell at IPL 12 nesting into the tick): 61 minutes of alternating echo floods, 241 fresh
connections and 9.76 million echoes per core, 15,493 + 9,304 nested interrupt entries, no fault,
no Data Abort, no lost wake-up. The e² studio 2026-10 window itself was then driven by hand
(2026-11-13): Debug Configurations, **CR8 core0 via OpenOCD dmem**, Debug; the session attaches
with the call stack and source of the idle task, a breakpoint set in the editor on
`angle_to_pulse_us()` hits, Step Over updates the Variables view, a second session on core1 runs
next to it, and closing e² studio resumes both cores and stops OpenOCD. On Linux, all six
variants build with `build.sh` and e² studio 2026-10. Not re-run with 4.3.0: typing the password
into the app window and pressing its buttons with the mouse (the window was built in-process
instead: fields, the three languages, and Connect without a password, which reports that `sudo`
needs one), the e² studio GUI session on a Linux host, and two simultaneous echo floods (one
per core), which stall the A55 clients after about 23,000 messages with the 3.1.0 firmware as
well. Upgrading from v1.0.x: the app keeps the e² studio folder and the workspace in
`%APPDATA%\cr8-debug\config.json`. When those settings name an install without the RZ FSP 4.x
packs and a newer install is present, the app switches to the newer one and to a new workspace
(`<old workspace>-fsp4`), says so in its log, and leaves the old workspace alone.

Windows host (Windows 10, e² studio 2025-01, Python 3.13): verified with the clickable app,
`e2studio/windows/cr8_debug_app.py`: password login, EVK-side install from the app, firmware
+ OpenOCD start, `arm-none-eabi-gdb.exe` attach / conditional hardware breakpoint / step /
variables through the app's own tunnel, redeploy of a Windows-built ELF
(`firmware/tools/build.ps1`), graceful stop. Port forwards made by Windows `ssh.exe` did not
work with gdb (connections dropped), which is why the app tunnels in-process. Not yet tried:
building the project from the e² studio GUI instead of the headless script.

## FSP 4.3.0 (done 2026-11-12)

The nested-interrupt bug this repository used to work around with a replacement `portASM.asm`
was reported upstream as [renesas/rz-fsp#3](https://github.com/renesas/rz-fsp/issues/3) and is
fixed in **RZ FSP v4.3.0** (released 2026-11-12, [release
page](https://github.com/renesas/rz-fsp/releases/tag/v4.3.0): `lr_svc` preserved across the
nested call, AAPCS 8-byte stack alignment in the dispatch path). The firmware now builds with
**e² studio 2026-10 + RZ FSP 4.3.0**; the 3.1.0 line is no longer supported by the build
scripts (`tools/migrate_cfg_430.py` is the one-shot migration that was applied to
`firmware/base/` and `firmware/cm33_demo/`).

What is still patched into the 4.3.0 packs, and why, is in
[docs/build-firmware.md](docs/build-firmware.md). The one piece that matters for nested
interrupts: the 4.3.0 handler has no interrupt-nesting count, so an inner interrupt that
requests a yield switches context while the outer ISR is still in progress. `patch_packs.py`
restores the upstream FreeRTOS ARM_CRx bookkeeping (count on entry, `switch_before_exit` only at
level 0) as a minimal edit of the 4.3.0 file. Reported upstream as
[renesas/rz-fsp#34](https://github.com/renesas/rz-fsp/issues/34); the measurements behind it
(the unmodified handler crashes the core within seconds once a nested ISR requests a yield, the
count prevents it) are in [firmware/experiments/nested-yield](firmware/experiments/nested-yield/README.md).

Renesas support added (November 2026) that the Multi-OS Package route needs no image change:
only the FSP source version referenced by the Multi-OS FSP tree moves from 4.2.0 to 4.3.0, with
the `src/` folder untouched. That is the path for projects built from the rz-fsp sources; this
repository builds from the e² studio packs.

## Authors

- [dragon1126](https://github.com/dragon1126) -- design, hardware bring-up, verification on the EVK, maintainer
- NFUEE0102 lab account -- repository host; commits before v1.0.0 were pushed from it
- Built with Claude Code (Anthropic) as pair programmer

## License

Our code and documentation: BSD-3-Clause ([LICENSE](LICENSE)). The repository also contains
Renesas template projects and FSP files (BSD-3-Clause), FreeRTOS port files (MIT) and an
OpenOCD patch (GPL-2.0-or-later); see [NOTICE.md](NOTICE.md). No Renesas proprietary binaries
are included.

---

## 快速開始（繁體中文）

這個專案讓 RZ/V2H 用自己的 A55 Linux 當除錯器，對 Cortex-R8 做原始碼級單步除錯，不需要
J-Link。

1. **EVK 端**：DSW1-7 撥 ON 後斷電重開；clone 本專案，執行 `bash debug/install-on-evk.sh`
   （有從 Releases 下載 `openocd-rzv2h-aarch64.tar.gz` 放進 `debug/` 的話幾秒就好，沒有的話會
   自己編譯約 10 分鐘）。
2. **開發機（Linux + e² studio 2026-10 + RZ FSP 4.3.0）**：clone 本專案，執行
   `bash e2studio/install-host.sh`，依提示輸入 EVK 的 IP、帳號、密碼；它會裝 `gdb-multiarch`、
   建置示範韌體、匯入 e² studio 工作區、放三顆桌面按鈕。
   **Windows 開發機**：解壓後，從 Releases 頁下載 `CR8DebugApp.exe` 放進資料夾直接點（或點
   `CR8-Debug-App.cmd`，需要 Python 3）；要在 PC 上建韌體就跑一次 `windows-setup.cmd`。**CR8 Debug App**：一個視窗輸入板子 IP、帳號、密碼 → 登入 → 板子端沒裝過就
   自動上傳安裝 → 啟動韌體與 OpenOCD → 用同一條 SSH 連線開出 gdb 埠 → 開 Windows 的 e² studio；
   關掉 e² studio 就自動收尾。不需要金鑰。兩顆 R8 可同時除錯（core0 走 3333、core1 走 3334，
   e² studio 開兩個 Debug 設定）。介面有繁中、英文、日文三種語言。見 [docs/windows-host.md](docs/windows-host.md)。
3. 點桌面的 **CR8 Debug (e2 studio)** → 在 e² studio 裡 Run → Debug Configurations →
   GDB Hardware Debugging → **CR8 core0 via OpenOCD dmem** → Debug。

三條鐵律：DSW1-7 一定要 ON 才上電；CR8 沒啟動前不要碰 `0x1F8xxxxx`（會卡死整板）；OpenOCD
開著時不要重啟 CR8（先按 **CR8 Debug STOP**，或用 **CR8 Redeploy**）。

展示腳本（含埋好的 bug、單步看見錯誤、現場改值、改碼重部署）見
[examples/demo_servo/DEMO.zh-TW.md](examples/demo_servo/DEMO.zh-TW.md)。
