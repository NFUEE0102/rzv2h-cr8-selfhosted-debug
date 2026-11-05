# -*- coding: utf-8 -*-
"""CR8 Debug - one-click Windows front end for the self-hosted RZ/V2H CR8 debugger.

What it does, all inside this process (no ssh.exe, no keys needed):
  1. asks for the EVK address, user and password (optionally remembered);
  2. logs in over SSH (paramiko) and, if the board is not set up yet, uploads the A55-side
     package (debug/, board scripts, demo firmware, prebuilt OpenOCD if present) and runs
     debug/install-on-evk.sh there;
  3. starts the firmware if core0 is offline and starts OpenOCD on the A55;
  4. opens the gdb ports (3333 core0, 3334 core1) on this PC through the SSH connection;
  5. launches e2 studio on the configured workspace; when e2 studio exits, resumes the cores,
     shuts OpenOCD down and closes the connection.
"Redeploy" uploads the ELF e2 studio built and restarts core0 with it.

Run:  py -3 cr8_debug_app.py        (needs:  py -3 -m pip install paramiko)
"""
import json
import os
import queue
import select
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import paramiko
except ImportError:  # pragma: no cover
    tk.Tk().withdraw()
    messagebox.showerror("CR8 Debug", "paramiko is missing:\n\n    py -3 -m pip install paramiko")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CONFIG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "cr8-debug", "config.json")
PROJ = "rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo"      # Eclipse name of the core0 project (also the artifact name of both)
PROJ1 = "rzv2h_rdk_cr8_core1_rpmsg_linux_rtos_demo"     # Eclipse name build.ps1 gives the core1 project
PORTS = (3333, 3334)                                     # gdb ports: core0, core1
LAUNCH = {0: "CR8 core0 via OpenOCD dmem.launch", 1: "CR8 core1 via OpenOCD dmem.launch"}
DEMO_ELF = os.path.join(REPO, "examples", "demo_servo", "cr8_demo.elf")


def find_tarball():
    for d in ("debug", ".release"):
        p = os.path.join(REPO, d, "openocd-rzv2h-aarch64.tar.gz")
        if os.path.isfile(p):
            return p
    return None
OCD_DIR = "/home/{user}/r8ocd"


def find_e2studio():
    for root in (r"C:\Renesas\rzv", r"C:\Renesas"):
        if os.path.isdir(root):
            for d in sorted(os.listdir(root), reverse=True):
                p = os.path.join(root, d)
                if os.path.isfile(os.path.join(p, "eclipse", "e2studio.exe")):
                    return p
    return r"C:\Renesas\rzv\e2studio_v2025-01_fsp_v3.1.0"


def find_gdb(e2s):
    for dp, _, fn in os.walk(os.path.join(e2s, "toolchains")):
        if "arm-none-eabi-gdb.exe" in fn:
            return os.path.join(dp, "arm-none-eabi-gdb.exe")
    return "arm-none-eabi-gdb"


DEFAULTS = {
    "host": "192.168.1.177",  # ci:allow-ip (default shown in the dialog)
    "user": "ubuntu", "remember": False, "password": "",
    "fw": "cr8_demo.elf",
    "project_dir": os.path.join(REPO, "firmware", "build", "core0-demo"),
    "fw1": "cr8_core1_demo.elf",
    "project1_dir": os.path.join(REPO, "firmware", "build", "core1-uart"),
    "e2studio": find_e2studio(),
    "workspace": os.path.join(os.path.expanduser("~"), "cr8dbg-workspace"),
    "auto_stop": True,
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    out = dict(cfg)
    if not out.get("remember"):
        out["password"] = ""
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


# ------------------------------------------------------------------ SSH side
class Evk:
    """SSH session to the EVK: commands, sudo, file upload, port forwarding."""

    def __init__(self, host, user, password, log):
        self.host, self.user, self.password, self.log = host, user, password, log
        self.cli = paramiko.SSHClient()
        self.cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.cli.connect(host, username=user, password=password, timeout=10,
                         allow_agent=False, look_for_keys=True, banner_timeout=15)
        self.ocd = OCD_DIR.format(user=user)
        self.forwarders = []
        # sudo is needed for firmware/OpenOCD control: check it once, now, with the password given
        if self.run("sudo -n true")[0] != 0:
            if not password:
                raise RuntimeError("logged in with an SSH key, but sudo on the EVK needs the password: fill in the password field")
            if self.run("true", sudo=True)[0] != 0:
                raise RuntimeError("sudo refused the password on the EVK")

    def run(self, cmd, sudo=False, timeout=120):
        """run a shell command; returns (rc, output). sudo feeds the password on stdin."""
        if sudo:
            cmd = "sudo -S -p '' sh -c " + sh_quote(cmd)
        stdin, stdout, stderr = self.cli.exec_command(cmd, timeout=timeout)
        if sudo:
            stdin.write(self.password + "\n")
            stdin.flush()
        stdin.channel.shutdown_write()   # EOF: a wrong/empty sudo password fails instead of waiting forever
        out = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
        return stdout.channel.recv_exit_status(), out.strip()

    def put(self, local, remote):
        sftp = self.cli.open_sftp()
        try:
            sftp.put(local, remote)
        finally:
            sftp.close()

    def put_tree(self, local_dir, remote_dir, names=None):
        sftp = self.cli.open_sftp()
        try:
            for n in sorted(os.listdir(local_dir)):
                p = os.path.join(local_dir, n)
                if os.path.isfile(p) and (names is None or n in names):
                    sftp.put(p, f"{remote_dir}/{n}")
        finally:
            sftp.close()

    # -- state -------------------------------------------------------------
    def installed(self):
        rc, _ = self.run(f"test -x {self.ocd}/r8ocd.sh && test -x {self.ocd}/board/start-cr8.sh && command -v openocd")
        return rc == 0

    def core0_state(self):
        return self.run("cat /sys/class/remoteproc/remoteproc1/state")[1]

    def core1_state(self):
        return self.run("cat /sys/class/remoteproc/remoteproc2/state 2>/dev/null || echo none")[1]

    FAULTS = {1: "reset", 2: "undefined instruction", 3: "prefetch abort", 4: "data abort", 5: "undefined instruction",
              6: "FreeRTOS assert", 7: "stack overflow", 8: "malloc failed"}

    def check_blackboxes(self):
        """read fault_type (+0x44) of both black boxes; log and return the cores that captured a fault"""
        out = self.run("for bb in 0x439F0044 0x441F0044; do busybox devmem $bb 32 2>/dev/null || echo 0; done", sudo=True)[1].split()
        bad = []
        for core, word in enumerate(out[:2]):
            try:
                v = int(word, 16)
            except ValueError:
                continue
            if v not in (0, 0xFFFFFFFF):
                bad.append(core)
                self.log(f"!! core{core} black box: fault_type {v} ({self.FAULTS.get(v, 'unknown')}) -> the core is in its abort handler; press Redeploy to restart the pair")
        return bad

    def ocd_running(self):
        return self.run("pgrep -x openocd")[0] == 0

    def debug_gate_open(self):
        rc, out = self.run("busybox devmem 0x10420C44 32", sudo=True)
        try:
            return bool(int(out.split()[-1], 16) & (1 << 12))
        except (ValueError, IndexError):
            return False

    # -- actions -----------------------------------------------------------
    def install(self, fw_elf, tarball):
        """upload debug/ + board helpers + demo ELF (+ prebuilt OpenOCD) and run install-on-evk.sh"""
        home = f"/home/{self.user}"
        self.log("uploading the A55-side package to ~/cr8-install ...")
        self.run("rm -rf ~/cr8-install && mkdir -p ~/cr8-install/debug ~/cr8-install/firmware/tools/board ~/cr8-install/examples/demo_servo")
        self.put_tree(os.path.join(REPO, "debug"), "cr8-install/debug")            # sftp paths: relative to $HOME
        self.put_tree(os.path.join(REPO, "firmware", "tools", "board"), "cr8-install/firmware/tools/board")
        if fw_elf and os.path.isfile(fw_elf):
            self.put(fw_elf, "cr8-install/examples/demo_servo/cr8_demo.elf")
        if tarball and os.path.isfile(tarball):
            self.log(f"uploading the prebuilt OpenOCD ({os.path.getsize(tarball) // 1000000} MB) ...")
            self.put(tarball, "cr8-install/debug/openocd-rzv2h-aarch64.tar.gz")
        else:
            self.log("no prebuilt openocd-rzv2h-aarch64.tar.gz in the repo's debug/ or .release/: the EVK builds it (~10 min)")
        self.log("running install-on-evk.sh on the EVK (as root, HOME kept) ...")
        # The script calls sudo itself and installs into $HOME/r8ocd; without a tty the sudo
        # timestamp cannot be shared, so run the whole script as root with HOME pointed at the
        # user and hand the result back to the user afterwards.
        rc, out = self.run(f"chmod +x {home}/cr8-install/debug/*.sh {home}/cr8-install/firmware/tools/board/*.sh; "
                           f"cd {home}/cr8-install && HOME={home} bash debug/install-on-evk.sh; rc=$?; "
                           f"chown -R {self.user}: {home}/r8ocd {home}/cr8-install; exit $rc", sudo=True, timeout=1500)
        for line in out.splitlines()[-14:]:
            self.log("  " + line)
        if rc != 0:
            raise RuntimeError("install-on-evk.sh failed (see log)")

    def start_cr8(self, fw, fw1=None):
        """(re)start core0 with fw (and core1 with fw1 when given). The CR8 cluster has no
        per-core reset: when the other core is running a single-core restart is refused by the
        board scripts, so both cores go down and up again (restart-r8-pair.sh).
        Never call this while OpenOCD runs."""
        core1_state, core1_fw = (self.run("cat /sys/class/remoteproc/remoteproc2/state /sys/class/remoteproc/remoteproc2/firmware")[1].split() + ["none", ""])[:2]
        if fw1 or core1_state == "running":
            fw1 = fw1 or core1_fw
            self.log(f"restarting the pair: core0 {fw} + core1 {fw1} (no per-core reset on the CR8)")
            rc, out = self.run(f"{self.ocd}/board/restart-r8-pair.sh {fw} {fw1}", sudo=True, timeout=120)
            want1 = True
        else:
            rc, out = self.run(f"{self.ocd}/board/start-cr8.sh {fw}", sudo=True, timeout=90)
            want1 = False
        for line in out.splitlines()[-4:]:
            self.log("  " + line)
        if self.core0_state() != "running" or (not want1 and rc != 0):
            raise RuntimeError("CR8 core0 did not come up (see log)")
        if want1 and self.core1_state() != "running":
            raise RuntimeError("CR8 core1 did not come up (see log)")

    def start_firmware(self, fw, fw1=None):
        """make sure core0 runs (start fw if offline); then core1 if fw1 is given and installed"""
        st = self.core0_state()
        if st == "running":
            self.log(f"CR8 core0 running ({self.run('cat /sys/class/remoteproc/remoteproc1/firmware')[1]})")
        else:
            self.log(f"CR8 core0 is '{st}' -> starting {fw}")
            self.start_cr8(fw)
        st1 = self.core1_state()
        if st1 == "running":
            self.log(f"CR8 core1 running ({self.run('cat /sys/class/remoteproc/remoteproc2/firmware')[1]})")
        elif fw1 and st1 != "none" and self.run(f"test -f /lib/firmware/{fw1}")[0] == 0:
            self.log(f"CR8 core1 is '{st1}' -> starting {fw1}")
            rc, out = self.run(f"{self.ocd}/board/start-cr8-core1.sh {fw1}", sudo=True, timeout=90)
            for line in out.splitlines()[-3:]:
                self.log("  " + line)
            if self.core1_state() != "running":
                self.log("core1 did not start; core0 debugging still works (core1 session will have nothing to attach to)")

    def start_openocd(self):
        if self.ocd_running():
            self.log("OpenOCD already running")
            return
        if not self.debug_gate_open():
            raise RuntimeError("CR8 debug APB not ready (CPG_LP_CR8_CTL3 bit12=0): is the CR8 started? MD_BOOT3 (DSW1-7) ON?")
        self.run(f"cd {self.ocd} && : > ocd.log && nohup ./r8ocd.sh >> ocd.log 2>&1 &", sudo=True, timeout=20)
        for _ in range(30):
            time.sleep(1)
            _, log = self.run(f"grep -v '^Debug' {self.ocd}/ocd.log | tail -20")
            if "Listening on port 3333" in log and self.ocd_running():
                self.log("OpenOCD started (Examination succeed)")
                return
            if "Refusing" in log or "Error" in log or "not found" in log:
                raise RuntimeError("OpenOCD failed to start:\n" + log)
        raise RuntimeError("OpenOCD did not start listening")

    def stop_openocd(self):
        if not self.ocd_running():
            return
        self.log("stopping OpenOCD (resume all cores, shutdown)")
        self.run("printf 'targets rzv2h.cr8_0\\nresume\\ntargets rzv2h.cr8_1\\nresume\\nshutdown\\n' | timeout 10 nc -q2 127.0.0.1 4444 >/dev/null 2>&1; true")
        for _ in range(5):
            if not self.ocd_running():
                return
            time.sleep(1)
        self.run("pkill -TERM openocd", sudo=True)
        time.sleep(1)
        if self.ocd_running():
            self.run("pkill -KILL openocd", sudo=True)

    def redeploy(self, patched_elf, fw, patched_elf1=None, fw1=None):
        """install the new ELF(s) and restart: core0 alone, or the pair when core1 is involved"""
        was = self.ocd_running()
        self.stop_openocd()
        for elf, name in ((patched_elf, fw), (patched_elf1, fw1)):
            if not elf:
                continue
            self.log(f"uploading {name} ...")
            self.put(elf, f"/tmp/{name}")
            rc, out = self.run(f"install -m 644 /tmp/{name} /lib/firmware/{name}", sudo=True)
            if rc != 0:
                raise RuntimeError("could not install the firmware: " + out)
        self.start_cr8(fw, fw1 if patched_elf1 else None)
        if was:
            self.start_openocd()

    # -- port forwarding ----------------------------------------------------
    def forward(self, port):
        f = Forwarder(self.cli.get_transport(), port, self.log)
        f.start()
        self.forwarders.append(f)

    def close(self):
        for f in self.forwarders:
            f.stop()
        self.forwarders = []
        try:
            self.cli.close()
        except Exception:
            pass


def sh_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


class Forwarder(threading.Thread):
    """127.0.0.1:<port> on this PC -> 127.0.0.1:<port> on the EVK, over the SSH transport."""

    def __init__(self, transport, port, log):
        super().__init__(daemon=True)
        self.transport, self.port, self.log = transport, port, log
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port))
        self.srv.listen(4)
        self.alive = True

    def run(self):
        while self.alive:
            try:
                self.srv.settimeout(0.5)
                client, peer = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                chan = self.transport.open_channel("direct-tcpip", ("127.0.0.1", self.port), peer)
            except Exception as e:  # noqa: BLE001
                self.log(f"forward {self.port}: {e}")
                client.close()
                continue
            threading.Thread(target=self.pump, args=(client, chan), daemon=True).start()

    def pump(self, client, chan):
        client.setblocking(True)
        try:
            while self.alive:
                r, _, _ = select.select([client, chan], [], [], 1.0)
                if client in r:
                    data = client.recv(16384)
                    if not data:
                        break
                    chan.sendall(data)
                if chan in r:
                    data = chan.recv(16384)
                    if not data:
                        break
                    client.sendall(data)
        except (OSError, EOFError):
            pass
        finally:
            try:
                chan.close()
            finally:
                client.close()

    def stop(self):
        self.alive = False
        try:
            self.srv.close()
        except OSError:
            pass


# ------------------------------------------------------------------ host side
def projects(cfg):
    """(core, project dir, Eclipse project name, firmware name) for every project that exists"""
    out = [(0, cfg["project_dir"], PROJ, cfg["fw"])]
    if cfg.get("project1_dir") and os.path.isfile(os.path.join(cfg["project1_dir"], ".project")):
        out.append((1, cfg["project1_dir"], PROJ1, cfg["fw1"]))
    return out


def prepare_launch(cfg):
    """copy the launch configuration(s) into the project(s) with e2 studio's own gdb"""
    gdb = find_gdb(cfg["e2studio"])   # plain backslashes: this is XML, not sed
    for core, pdir, _, _ in projects(cfg):
        if not os.path.isdir(pdir):
            continue
        with open(os.path.join(REPO, "e2studio", LAUNCH[core]), encoding="utf-8") as f:
            text = f.read().replace('DEBUG_NAME" value="gdb-multiarch"', f'DEBUG_NAME" value="{gdb}"')
        with open(os.path.join(pdir, LAUNCH[core]), "w", encoding="utf-8") as f:
            f.write(text)


def ensure_workspace(cfg, log):
    """import the firmware projects into the workspace (headless) if it does not hold them yet"""
    ws = cfg["workspace"]
    meta = os.path.join(ws, ".metadata", ".plugins", "org.eclipse.core.resources", ".projects")
    missing = [(pdir, name) for _, pdir, name, _ in projects(cfg) if not os.path.isdir(os.path.join(meta, name))]
    if not missing:
        return
    if os.path.isfile(os.path.join(ws, ".metadata", ".lock")):
        try:
            os.remove(os.path.join(ws, ".metadata", ".lock"))   # stale lock from a closed e2 studio
        except OSError:
            raise RuntimeError(f"workspace {ws} is in use (e2 studio open?) and lacks {', '.join(n for _, n in missing)}: close e2 studio and retry") from None
    exe = os.path.join(cfg["e2studio"], "eclipse", "e2studioc.exe")
    log(f"workspace lacks {', '.join(n for _, n in missing)} -> importing (headless e2 studio, ~30 s)")
    os.makedirs(ws, exist_ok=True)
    args = [exe, "-nosplash", "-data", ws, "-application", "org.eclipse.cdt.managedbuilder.core.headlessbuild",
            "-import", os.path.join(REPO, "firmware", "cm33_demo")]
    for pdir, _ in missing:
        args += ["-import", pdir]
    r = subprocess.run(args + ["-no-indexer"], capture_output=True, text=True, timeout=600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    still = [n for _, n in missing if not os.path.isdir(os.path.join(meta, n))]
    if still:
        raise RuntimeError(f"headless import did not register {', '.join(still)}: " + (r.stdout + r.stderr)[-800:])
    log("project(s) imported into the workspace")


def patch_elf(cfg, log, core=0):
    """post-process a copy of the ELF e2 studio built (zero-size DDR PT_LOADs -> PT_NULL;
    core1 additionally nulls the 4-byte PT_LOAD at 0x081BFFFC, as build.ps1 does)"""
    pdir = cfg["project_dir"] if core == 0 else cfg["project1_dir"]
    fw = cfg["fw"] if core == 0 else cfg["fw1"]
    src = os.path.join(pdir, "Debug", PROJ + ".elf")      # the artifact keeps the core0 name in both projects
    if not os.path.isfile(src):
        raise RuntimeError(f"ELF not found: {src}\nBuild first: Project -> Build Project (Ctrl+B) in e2 studio")
    age = int(time.time() - os.path.getmtime(src))
    log(f"core{core} ELF built {age // 60} min {age % 60} s ago")
    dst = os.path.join(os.environ.get("TEMP", "."), fw)
    with open(src, "rb") as f, open(dst, "wb") as g:
        g.write(f.read())
    tools = os.path.join(REPO, "firmware", "tools")
    steps = [[sys.executable, os.path.join(tools, "patch-elf-phdr.py"), dst]]
    if core == 1:
        steps.append([sys.executable, os.path.join(tools, "null_phdr_at.py"), dst, "0x081BFFFC"])
    for cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(os.path.basename(cmd[1]) + " failed:\n" + r.stdout + r.stderr)
    return dst


def have_elf(cfg, core):
    pdir = cfg["project_dir"] if core == 0 else cfg.get("project1_dir", "")
    return bool(pdir) and os.path.isfile(os.path.join(pdir, "Debug", PROJ + ".elf"))


# ------------------------------------------------------------------ GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CR8 Debug - RZ/V2H self-hosted debugger")
        self.resizable(True, True)
        self.cfg = load_config()
        self.evk = None
        self.e2s = None
        self.q = queue.Queue()
        self.busy = False
        self._build()
        self.after(100, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        f = ttk.Frame(self, padding=10)
        f.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.v = {}

        def row(r, label, key, show=None, width=44, browse=None):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(self.cfg.get(key, "")))
            e = ttk.Entry(f, textvariable=var, width=width, show=show)
            e.grid(row=r, column=1, sticky="we", pady=2)
            self.v[key] = var
            if browse:
                ttk.Button(f, text="...", width=3, command=lambda: self._browse(var, browse)).grid(row=r, column=2, padx=2)

        row(0, "EVK IP / 板子位址", "host")
        row(1, "帳號 / user", "user")
        row(2, "密碼 / password", "password", show="*")
        self.v["remember"] = tk.BooleanVar(value=bool(self.cfg.get("remember")))
        ttk.Checkbutton(f, text="記住密碼（存在 %APPDATA%\\cr8-debug，只有你這個帳號讀得到）", variable=self.v["remember"]).grid(row=3, column=1, sticky="w")
        row(4, "core0 韌體 / fw on EVK", "fw")
        row(5, "core0 專案 / project", "project_dir", browse="dir")
        row(6, "core1 韌體 / fw1 on EVK", "fw1")
        row(7, "core1 專案 / project1（可空）", "project1_dir", browse="dir")
        row(8, "e² studio 安裝目錄", "e2studio", browse="dir")
        row(9, "工作區 / workspace", "workspace", browse="dir")
        self.v["auto_stop"] = tk.BooleanVar(value=bool(self.cfg.get("auto_stop", True)))
        ttk.Checkbutton(f, text="關掉 e² studio 時自動收尾（resume、停 OpenOCD、斷線）", variable=self.v["auto_stop"]).grid(row=10, column=1, sticky="w")

        b = ttk.Frame(f)
        b.grid(row=11, column=0, columnspan=3, pady=8, sticky="w")
        self.btn_go = ttk.Button(b, text="連線並開始除錯 / Connect & Debug", command=self.go)
        self.btn_go.pack(side="left", padx=3)
        self.btn_redeploy = ttk.Button(b, text="重新部署韌體 / Redeploy (core0+core1)", command=self.redeploy)
        self.btn_redeploy.pack(side="left", padx=3)
        self.btn_stop = ttk.Button(b, text="收尾 / Stop", command=self.stop)
        self.btn_stop.pack(side="left", padx=3)
        self.btn_install = ttk.Button(b, text="安裝到板子 / Install on EVK", command=self.install)
        self.btn_install.pack(side="left", padx=3)

        self.txt = tk.Text(f, height=16, width=96, state="disabled", font=("Consolas", 9))
        self.txt.grid(row=12, column=0, columnspan=3, sticky="nsew")
        f.rowconfigure(12, weight=1)
        f.columnconfigure(1, weight=1)
        self.status = tk.StringVar(value="ready")
        ttk.Label(f, textvariable=self.status).grid(row=13, column=0, columnspan=3, sticky="w")

    def _browse(self, var, kind):
        p = filedialog.askdirectory(initialdir=var.get() or os.path.expanduser("~"))
        if p:
            var.set(p.replace("/", "\\"))

    # -- logging from worker threads --------------------------------------
    def log(self, msg):
        self.q.put(msg)

    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if isinstance(msg, tuple):
                    if msg[0] == "quit":
                        self.destroy()
                        return
                    self.log("e2 studio closed -> stopping")
                    self.stop()
                    continue
                self.txt.configure(state="normal")
                self.txt.insert("end", time.strftime("%H:%M:%S ") + msg + "\n")
                self.txt.see("end")
                self.txt.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _collect(self):
        for k, var in self.v.items():
            self.cfg[k] = var.get()
        save_config(self.cfg)
        if not self.cfg["host"] or not self.cfg["user"]:
            raise RuntimeError("EVK address and user are required")

    def _work(self, fn, done=None):
        if self.busy:
            messagebox.showinfo("CR8 Debug", "busy - wait for the current step to finish")
            return
        self.busy = True
        self.status.set("working ...")

        def runner():
            try:
                fn()
                self.q.put("ok")
                if done:
                    done()
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self.q.put("ERROR: " + msg)
                self.after(0, lambda: messagebox.showerror("CR8 Debug", msg))
            finally:
                self.busy = False
                self.after(0, lambda: self.status.set("ready"))
        threading.Thread(target=runner, daemon=True).start()

    def _connect(self):
        if self.evk:
            try:
                self.evk.run("true")
                return
            except Exception:  # noqa: BLE001
                self.evk = None
        self.log(f"connecting to {self.cfg['user']}@{self.cfg['host']} ...")
        try:
            self.evk = Evk(self.cfg["host"], self.cfg["user"], self.cfg["password"], self.log)
        except paramiko.AuthenticationException:
            raise RuntimeError("login failed: check the user name and password") from None
        except (socket.error, paramiko.SSHException) as e:
            raise RuntimeError(f"cannot reach {self.cfg['host']}: {e}") from None
        self.log("logged in")

    # -- buttons ------------------------------------------------------------
    def go(self):
        try:
            self._collect()
        except RuntimeError as e:
            messagebox.showerror("CR8 Debug", str(e))
            return

        def work():
            self._connect()
            if not self.evk.installed():
                self.log("EVK not set up yet -> installing (once)")
                self.evk.install(DEMO_ELF, find_tarball())
            self.evk.start_firmware(self.cfg["fw"], self.cfg.get("fw1") or None)
            if self.evk.check_blackboxes():
                raise RuntimeError("a CR8 core is sitting in its abort handler: press Redeploy (restarts the pair), then Connect again")
            self.evk.start_openocd()
            for p in PORTS:
                self.evk.forward(p)
            self.log(f"gdb ports open on this PC: {PORTS[0]} (core0), {PORTS[1]} (core1)")
            prepare_launch(self.cfg)
            exe = os.path.join(self.cfg["e2studio"], "eclipse", "e2studio.exe")
            if not os.path.isfile(exe):
                raise RuntimeError(f"e2 studio not found: {exe}")
            ensure_workspace(self.cfg, self.log)
            names = " / ".join(f"'{LAUNCH[c][:-7]}'" for c, _, _, _ in projects(self.cfg))
            self.log(f"starting e2 studio ... Run -> Debug Configurations -> GDB Hardware Debugging -> {names}")
            self.e2s = subprocess.Popen([exe, "-data", self.cfg["workspace"]])
            if self.cfg.get("auto_stop", True):
                threading.Thread(target=self._watch_e2s, daemon=True).start()
        self._work(work)

    def _watch_e2s(self):
        self.e2s.wait()
        self.q.put(("stop",))  # handed to the Tk thread by _drain

    def stop(self):
        def work():
            if self.evk:
                self.evk.stop_openocd()
                self.log(f"CR8 core0: {self.evk.core0_state()}, core1: {self.evk.core1_state()}")
                self.evk.check_blackboxes()
                self.evk.close()
                self.evk = None
                self.log("disconnected")
            else:
                self.log("nothing to stop")
        self._work(work)

    def redeploy(self):
        try:
            self._collect()
        except RuntimeError as e:
            messagebox.showerror("CR8 Debug", str(e))
            return

        def work():
            elf = patch_elf(self.cfg, self.log)
            elf1 = patch_elf(self.cfg, self.log, 1) if have_elf(self.cfg, 1) else None
            self._connect()
            self.evk.redeploy(elf, self.cfg["fw"], elf1, self.cfg.get("fw1"))
            self.log("redeployed; press Debug again in e2 studio")
        self._work(work)

    def install(self):
        try:
            self._collect()
        except RuntimeError as e:
            messagebox.showerror("CR8 Debug", str(e))
            return

        def work():
            # prefer the ELF built here (its sources resolve in this e2 studio) over the repo's prebuilt one
            elf = patch_elf(self.cfg, self.log) if have_elf(self.cfg, 0) else DEMO_ELF
            self._connect()
            self.evk.install(elf, find_tarball())
            if have_elf(self.cfg, 1):
                elf1 = patch_elf(self.cfg, self.log, 1)
                self.evk.put(elf1, f"/tmp/{self.cfg['fw1']}")
                self.evk.run(f"install -m 644 /tmp/{self.cfg['fw1']} /lib/firmware/{self.cfg['fw1']}", sudo=True)
                self.log(f"installed core1 firmware {self.cfg['fw1']}")
            if elf != DEMO_ELF:
                self.log("installed the ELF(s) built here; loaded on the next (re)start -> press Redeploy to run them now")
        self._work(work)

    def _on_close(self):
        """closing the window = Stop: resume the cores, shut OpenOCD down, disconnect, then exit.
        e2 studio (if still open) is left alone; its gdb session just reports a disconnect."""
        if not self.evk:
            self.destroy()
            return
        self.status.set("closing: stopping OpenOCD on the EVK ...")
        for b in (self.btn_go, self.btn_redeploy, self.btn_stop, self.btn_install):
            b.configure(state="disabled")

        def work():
            try:
                self.evk.stop_openocd()
                self.log(f"CR8 core0: {self.evk.core0_state()}")
            except Exception as e:  # noqa: BLE001
                self.log("stop failed: " + str(e))
            finally:
                try:
                    self.evk.close()
                finally:
                    self.q.put(("quit",))
        threading.Thread(target=work, daemon=True).start()

if __name__ == "__main__":
    App().mainloop()
