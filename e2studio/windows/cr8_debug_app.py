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
PROJ = "rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo"
PORTS = (3333, 3334)
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
    "host": "192.168.1.177", "user": "ubuntu",  # ci:allow-ip (default shown in the dialog) "remember": False, "password": "",
    "fw": "cr8_demo.elf",
    "project_dir": os.path.join(REPO, "firmware", "build", "core0-demo"),
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

    def run(self, cmd, sudo=False, timeout=120):
        """run a shell command; returns (rc, output). sudo feeds the password on stdin."""
        if sudo:
            cmd = "sudo -S -p '' sh -c " + sh_quote(cmd)
        stdin, stdout, stderr = self.cli.exec_command(cmd, timeout=timeout)
        if sudo:
            stdin.write(self.password + "\n")
            stdin.flush()
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

    def start_cr8(self, fw):
        """(re)start core0 with fw. The CR8 cluster has no per-core reset: when core1 is running,
        a single-core restart is refused by start-cr8.sh, so both cores go down and up again
        (restart-r8-pair.sh). Never call this while OpenOCD runs."""
        core1_state, core1_fw = self.run("cat /sys/class/remoteproc/remoteproc2/state /sys/class/remoteproc/remoteproc2/firmware")[1].split()[:2]
        if core1_state == "running":
            self.log(f"core1 is running ({core1_fw}) -> restarting the pair (no per-core reset on the CR8)")
            rc, out = self.run(f"{self.ocd}/board/restart-r8-pair.sh {fw} {core1_fw}", sudo=True, timeout=90)
        else:
            rc, out = self.run(f"{self.ocd}/board/start-cr8.sh {fw}", sudo=True, timeout=90)
        for line in out.splitlines()[-4:]:
            self.log("  " + line)
        if self.core0_state() != "running" or (core1_state != "running" and rc != 0):
            raise RuntimeError("CR8 core0 did not come up (see log)")

    def start_firmware(self, fw):
        st = self.core0_state()
        if st == "running":
            self.log(f"CR8 core0 running ({self.run('cat /sys/class/remoteproc/remoteproc1/firmware')[1]})")
            return
        self.log(f"CR8 core0 is '{st}' -> starting {fw}")
        self.start_cr8(fw)

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

    def redeploy(self, patched_elf, fw):
        was = self.ocd_running()
        self.stop_openocd()
        self.log(f"uploading {os.path.basename(patched_elf)} ...")
        self.put(patched_elf, f"/tmp/{fw}")
        rc, out = self.run(f"install -m 644 /tmp/{fw} /lib/firmware/{fw}", sudo=True)
        if rc != 0:
            raise RuntimeError("could not install the firmware: " + out)
        self.start_cr8(fw)
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
def prepare_launch(cfg):
    """copy the launch configuration into the project with e2 studio's own gdb"""
    src = os.path.join(REPO, "e2studio", "CR8 core0 via OpenOCD dmem.launch")
    dst = os.path.join(cfg["project_dir"], "CR8 core0 via OpenOCD dmem.launch")
    if not os.path.isdir(cfg["project_dir"]):
        return
    gdb = find_gdb(cfg["e2studio"])   # plain backslashes: this is XML, not sed
    with open(src, encoding="utf-8") as f:
        text = f.read().replace('DEBUG_NAME" value="gdb-multiarch"', f'DEBUG_NAME" value="{gdb}"')
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)


def ensure_workspace(cfg, log):
    """import the firmware projects into the workspace (headless) if it does not hold them yet"""
    ws = cfg["workspace"]
    marker = os.path.join(ws, ".metadata", ".plugins", "org.eclipse.core.resources", ".projects", PROJ)
    if os.path.isdir(marker):
        return
    if os.path.isfile(os.path.join(ws, ".metadata", ".lock")):
        try:
            os.remove(os.path.join(ws, ".metadata", ".lock"))   # stale lock from a closed e2 studio
        except OSError:
            raise RuntimeError(f"workspace {ws} is in use (e2 studio open?) and has no project yet: close e2 studio and retry") from None
    cm33 = os.path.join(REPO, "firmware", "cm33_demo")
    exe = os.path.join(cfg["e2studio"], "eclipse", "e2studioc.exe")
    log(f"workspace {ws} has no project yet -> importing (headless e2 studio, ~30 s)")
    os.makedirs(ws, exist_ok=True)
    r = subprocess.run([exe, "-nosplash", "-data", ws, "-application", "org.eclipse.cdt.managedbuilder.core.headlessbuild",
                        "-import", cm33, "-import", cfg["project_dir"], "-no-indexer"],
                       capture_output=True, text=True, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not os.path.isdir(marker):
        raise RuntimeError("headless import did not register the project: " + (r.stdout + r.stderr)[-800:])
    log("project imported into the workspace")


def patch_elf(cfg, log):
    """post-process a copy of the ELF e2 studio built (zero-size DDR PT_LOADs -> PT_NULL)"""
    src = os.path.join(cfg["project_dir"], "Debug", PROJ + ".elf")
    if not os.path.isfile(src):
        raise RuntimeError(f"ELF not found: {src}\nBuild first: Project -> Build Project (Ctrl+B) in e2 studio")
    age = int(time.time() - os.path.getmtime(src))
    log(f"ELF built {age // 60} min {age % 60} s ago")
    dst = os.path.join(os.environ.get("TEMP", "."), cfg["fw"])
    with open(src, "rb") as f, open(dst, "wb") as g:
        g.write(f.read())
    tool = os.path.join(REPO, "firmware", "tools", "patch-elf-phdr.py")
    r = subprocess.run([sys.executable, tool, dst], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("patch-elf-phdr failed:\n" + r.stdout + r.stderr)
    return dst


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
        row(4, "韌體檔名 / fw on EVK", "fw")
        row(5, "e² studio 專案 / project", "project_dir", browse="dir")
        row(6, "e² studio 安裝目錄", "e2studio", browse="dir")
        row(7, "工作區 / workspace", "workspace", browse="dir")
        self.v["auto_stop"] = tk.BooleanVar(value=bool(self.cfg.get("auto_stop", True)))
        ttk.Checkbutton(f, text="關掉 e² studio 時自動收尾（resume、停 OpenOCD、斷線）", variable=self.v["auto_stop"]).grid(row=8, column=1, sticky="w")

        b = ttk.Frame(f)
        b.grid(row=9, column=0, columnspan=3, pady=8, sticky="w")
        self.btn_go = ttk.Button(b, text="連線並開始除錯 / Connect & Debug", command=self.go)
        self.btn_go.pack(side="left", padx=3)
        self.btn_redeploy = ttk.Button(b, text="重新部署韌體 / Redeploy", command=self.redeploy)
        self.btn_redeploy.pack(side="left", padx=3)
        self.btn_stop = ttk.Button(b, text="收尾 / Stop", command=self.stop)
        self.btn_stop.pack(side="left", padx=3)
        self.btn_install = ttk.Button(b, text="安裝到板子 / Install on EVK", command=self.install)
        self.btn_install.pack(side="left", padx=3)

        self.txt = tk.Text(f, height=16, width=96, state="disabled", font=("Consolas", 9))
        self.txt.grid(row=10, column=0, columnspan=3, sticky="nsew")
        f.rowconfigure(10, weight=1)
        f.columnconfigure(1, weight=1)
        self.status = tk.StringVar(value="ready")
        ttk.Label(f, textvariable=self.status).grid(row=11, column=0, columnspan=3, sticky="w")

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
            self.evk.start_firmware(self.cfg["fw"])
            self.evk.start_openocd()
            for p in PORTS:
                self.evk.forward(p)
            self.log(f"gdb ports open on this PC: {PORTS[0]} (core0), {PORTS[1]} (core1)")
            prepare_launch(self.cfg)
            exe = os.path.join(self.cfg["e2studio"], "eclipse", "e2studio.exe")
            if not os.path.isfile(exe):
                raise RuntimeError(f"e2 studio not found: {exe}")
            ensure_workspace(self.cfg, self.log)
            self.log("starting e2 studio ... Run -> Debug Configurations -> GDB Hardware Debugging -> 'CR8 core0 via OpenOCD dmem'")
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
                self.log(f"CR8 core0: {self.evk.core0_state()}")
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
            self._connect()
            self.evk.redeploy(elf, self.cfg["fw"])
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
            elf = DEMO_ELF
            if os.path.isfile(os.path.join(self.cfg["project_dir"], "Debug", PROJ + ".elf")):
                elf = patch_elf(self.cfg, self.log)
            self._connect()
            self.evk.install(elf, find_tarball())
            if elf != DEMO_ELF:
                self.log("installed the ELF built here; it is loaded on the next core0 (re)start -> press Redeploy to run it now")
        self._work(work)

    def _on_close(self):
        if self.evk and self.evk.ocd_running():
            if messagebox.askyesno("CR8 Debug", "OpenOCD is still running on the EVK. Stop it and disconnect before closing?"):
                try:
                    self.evk.stop_openocd()
                except Exception:  # noqa: BLE001
                    pass
        if self.evk:
            self.evk.close()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
