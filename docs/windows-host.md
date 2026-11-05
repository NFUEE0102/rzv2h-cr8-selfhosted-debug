# Windows host: the clickable app

`e2studio/windows/cr8_debug_app.py` is a one-window front end for a Windows PC that has
e² studio (2025-01, FSP 3.1.0) installed. It needs no SSH key, no `ssh.exe`, no terminal:

1. you type the EVK address, user and password (tick "remember" to keep them in
   `%APPDATA%\cr8-debug\config.json`, readable only by your Windows account);
2. it logs in over SSH (the `paramiko` library, inside the app process);
3. if the board has no `~/r8ocd/` yet, it uploads `debug/`, the board helpers, the demo
   firmware and, when present, the prebuilt OpenOCD tarball, and runs
   `debug/install-on-evk.sh` there (as root with `HOME` kept, since there is no terminal for
   the script's own `sudo` prompts);
4. it starts the firmware if core0 is offline, starts OpenOCD, and opens the gdb ports on this
   PC (`127.0.0.1:3333` core0, `:3334` core1) **through the same SSH connection**;
5. it launches e² studio on the configured workspace. When you close e² studio it resumes
   both cores, shuts OpenOCD down and disconnects.

Buttons: **Connect & Debug** (the above), **Redeploy** (post-processes the ELF e² studio
built, uploads it, restarts core0, restarts OpenOCD), **Stop** (graceful tear-down),
**Install on EVK** (step 3 by hand).

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
| `firmware/tools/build.ps1` | Windows port of `build.sh` (headless e² studio build of a variant) |
| `debug/session.sh` | board-side single-session helper used by the `.ps1` launchers |

## Known limits

* The app trusts the EVK's host key on first contact (`AutoAddPolicy`); it is a lab board on
  a LAN.
* The password is sent to `sudo -S` on the EVK for the steps that need root (start firmware,
  start/stop OpenOCD, install). It is never written to disk unless "remember" is ticked.
* One app window = one board. Start a second instance for a second board (ports would clash,
  so change `PORTS` first).
