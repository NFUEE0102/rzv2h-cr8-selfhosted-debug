# Windows host: the clickable app

`e2studio/windows/cr8_debug_app.py` is a one-window front end for a Windows PC that has
e² studio (2026-10, RZ FSP 4.3.0) installed. It needs no SSH key, no `ssh.exe`, no terminal:

1. you type the EVK address, user and password (tick "remember" to keep them in
   `%APPDATA%\cr8-debug\config.json`, readable only by your Windows account);
2. it logs in over SSH (the `paramiko` library, inside the app process);
3. if the board has no `~/r8ocd/` yet, it uploads `debug/`, the board helpers, the demo
   firmware and, when present, the prebuilt OpenOCD tarball, and runs
   `debug/install-on-evk.sh` there (as root with `HOME` kept, since there is no terminal for
   the script's own `sudo` prompts);
4. it starts the firmware if core0 is offline, starts OpenOCD, and opens the gdb ports on this
   PC (`127.0.0.1:3333` core0, `:3334` core1) **through the same SSH connection**;
5. it launches e² studio on the configured workspace. When you close e² studio, or the app
   window itself, it resumes
   both cores, shuts OpenOCD down and disconnects.

Buttons: **Connect & Debug** (the above), **Redeploy** (post-processes the ELF e² studio
built, uploads it, restarts core0, restarts OpenOCD), **Stop** (graceful tear-down),
**Install on EVK** (step 3 by hand).

## Three ways to start it

| | What you need | How |
|---|---|---|
| **CR8DebugApp.exe** | nothing (Python and paramiko are inside) | download it from the Releases page into the unzipped repository folder (next to README.md) and double-click it, or double-click `CR8-Debug-App.cmd` |
| `CR8-Debug-App.cmd` | Python 3 (python.org) | double-click; installs paramiko on first run, then starts the app |
| Desktop shortcut | after `windows-setup.cmd` | **CR8 Debug App** on the Desktop |

The EXE looks for `debug/install-on-evk.sh` in its own folder and up to three parents, so it
can live in the repository root or in `e2studio\windows\`; alone in some other folder it
shows an error and exits. It is built with `e2studio\windows\build-exe.ps1` (PyInstaller,
one file, no console; about 16 MB) and attached to each release. Building the demo firmware
still needs Python (the FSP pack patch and the headless build driver), so `windows-setup.cmd`
stays a Python job; debugging a project that is already built does not.

## Setup (once)

```powershell
git clone https://github.com/NFUEE0102/rzv2h-cr8-selfhosted-debug.git
cd rzv2h-cr8-selfhosted-debug
# optional, saves the 10-minute OpenOCD build on the EVK:
#   download openocd-rzv2h-aarch64.tar.gz from the Releases page into debug\
powershell -ExecutionPolicy Bypass -File e2studio\windows\install-host.ps1
```

`install-host.ps1` asks for the EVK address etc., installs `paramiko` (`py -3 -m pip`), builds
the demo firmware project with the headless e² studio (`firmware\tools\build.ps1`, about a
minute), writes the launch configuration with e² studio's own `arm-none-eabi-gdb.exe` into the
project, imports it into the workspace and puts **CR8 Debug App** on the Desktop (plus the
three `ssh.exe`-based launchers below). Requirements: Python 3 from python.org (the `py`
launcher; the Microsoft Store stub does not work), e² studio under `C:\Renesas`.

Then: double-click **CR8 Debug App**, fill in IP / user / password, press **Connect & Debug**;
in e² studio: Run, Debug Configurations, GDB Hardware Debugging, **CR8 core0 via OpenOCD
dmem**, Debug.

## Upgrading from v1.0.x

v1.1.0 needs e² studio 2026-10 with RZ FSP 4.3.0; the older e² studio can stay installed next to
it. Install the new one, update the repository, and run `firmware\tools\build.ps1 core0-demo`
(and `core1-uart`) once. The app keeps the e² studio folder and the workspace in
`%APPDATA%\cr8-debug\config.json`, and saved values win over detected ones. So on its first start
after the upgrade it checks them: if the saved e² studio has no RZ FSP 4.x packs and a newer
install is present, it switches to the newer install and to a new workspace
(`<old workspace>-fsp4`), and writes both changes to its log. The old workspace is not touched.
Both fields can be edited back; settings chosen after the upgrade are not changed again.

## Languages

The app's labels, buttons, log lines and error dialogs come in Traditional Chinese, English
and Japanese. It starts in the Windows display language (zh-TW for Chinese, ja for Japanese,
English otherwise); the "Language" box at the top right switches at once and the choice is
stored in the config (`"lang"`). Output of the board-side scripts (`start-cr8.sh`,
`install-on-evk.sh`, black-box dump) is shown as it comes. All strings are in the `STR`
table at the top of `cr8_debug_app.py`; adding a language is one more column there plus an
entry in `LANGS`.

## Two cores at once

The EVK runs two Cortex-R8 cores; OpenOCD exposes them as two targets with their own gdb
ports (3333 core0, 3334 core1) and the app forwards both. The second project is optional:

* `firmware\tools\build.ps1 core1-uart` builds the core1 firmware (`cr8_core1_demo.elf`) and
  names its Eclipse project `rzv2h_rdk_cr8_core1_rpmsg_linux_rtos_demo`, so it can sit next
  to the core0 project in one workspace (both keep the artifact name
  `Debug\rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo.elf`).
* The app's "core1 專案 / project1" field points at it (default
  `firmware\build\core1-uart`; leave it empty for core0 only). On **Connect & Debug** the app
  imports both projects, writes both launch files (`CR8 core0 via OpenOCD dmem`,
  `CR8 core1 via OpenOCD dmem`) and starts core1 too when it is offline and its firmware is
  on the board.
* In e² studio start both configurations, one after the other: two debug sessions appear in
  the Debug view, each with its own breakpoints, stepping and variables.
* **Redeploy** installs and restarts both ELFs together. The CR8 cluster has no per-core
  reset, so any firmware change is a restart of the pair (both down, core0 up, core1 up).

Verified on Windows through the app's tunnels, two `arm-none-eabi-gdb.exe` sessions at the
same time: core1 halted at `r8_blackbox_pump` for 8 s while core0's 1 kHz tick kept
counting, then core0 halted at `angle_to_pulse_us` as well (both halted), then both detached
and both cores were running with clean black boxes. One caveat from that testing: in one of
about ten dual-session rounds both cores took a prefetch abort at the same moment (black box
fault_type 3 on both, garbage PCs, one core halted at a breakpoint and the other resuming);
it did not reproduce in five replays of the same sequence, including a sweep of attach/detach
overlaps, so the cause is unknown. The app now reads both black boxes on Connect and on
Stop and tells you to press Redeploy (pair restart) if a core sits in its abort handler.
Detaching one session resumes only that
core (the `gdb-detach` handler in `cr8-dmem.cfg` is per target); closing e² studio or the app
resumes both and shuts OpenOCD down.

## Why an in-process tunnel

Windows OpenSSH has no ControlMaster, so the Linux design (one password, many `ssh` calls on
a shared connection) does not carry over. The first Windows attempt
(`cr8-debug.ps1` + `debug/session.sh`: one `ssh -tt -L 3333:... session.sh start` session that
carries the tunnel, the sudo prompt and OpenOCD's lifetime) starts fine, but gdb connections
through the `ssh.exe` port forward were dropped by OpenOCD immediately
("Remote communication error. Target disconnected"), with both Windows OpenSSH 9.5 and Git's
ssh. The cause was not found. The app forwards the ports itself (`direct-tcpip` channels on
the paramiko transport); through that tunnel `arm-none-eabi-gdb.exe` attaches, hits a
conditional hardware breakpoint, steps and reads variables (verified, 2.5 s for the whole
batch). The `.ps1` launchers and `session.sh` are kept for reference and for hosts that do
have a working `ssh.exe` forward.

## Files

| File | Role |
|---|---|
| `e2studio/windows/cr8_debug_app.py` | the app (Tk + paramiko) |
| `e2studio/windows/install-host.ps1` | one-time host setup, Desktop shortcuts |
| `e2studio/windows/common.ps1`, `cr8-debug.ps1`, `cr8-stop.ps1`, `cr8-redeploy.ps1` | `ssh.exe`-based launchers (see above) |
| `firmware/tools/build.ps1` | Windows port of `build.sh` (headless e² studio build of a variant; core1 variants get their own project name) |
| `e2studio/CR8 core1 via OpenOCD dmem.launch` | second launch configuration, gdb port 3334, core1 project |
| `debug/session.sh` | board-side single-session helper used by the `.ps1` launchers |

## Known limits

* The app trusts the EVK's host key on first contact (`AutoAddPolicy`); it is a lab board on
  a LAN.
* The password is sent to `sudo -S` on the EVK for the steps that need root (start firmware,
  start/stop OpenOCD, install). It is never written to disk unless "remember" is ticked.
* One app window = one board. Start a second instance for a second board (ports would clash,
  so change `PORTS` first).
