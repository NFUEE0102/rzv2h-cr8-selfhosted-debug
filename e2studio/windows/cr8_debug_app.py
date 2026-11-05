# -*- coding: utf-8 -*-
"""CR8 Debug - one-click Windows front end for the self-hosted RZ/V2H CR8 debugger.

What it does, all inside this process (no ssh.exe, no keys needed):
  1. asks for the EVK address, user and password (optionally remembered);
  2. logs in over SSH (paramiko) and, if the board is not set up yet, uploads the A55-side
     package (debug/, board scripts, demo firmware, prebuilt OpenOCD if present) and runs
     debug/install-on-evk.sh there;
  3. starts the firmware if core0 is offline (and core1 when configured) and starts OpenOCD;
  4. opens the gdb ports (3333 core0, 3334 core1) on this PC through the SSH connection;
  5. launches e2 studio on the configured workspace; when e2 studio exits, resumes the cores,
     shuts OpenOCD down and closes the connection.
"Redeploy" uploads the ELF(s) e2 studio built and restarts the cores with them.

UI languages: Traditional Chinese, English, Japanese (follows the Windows display language,
or the "Language" box; stored in the config). All user-facing strings live in STR below;
output of the board-side scripts is shown as it comes.

Run:  py -3 cr8_debug_app.py        (needs:  py -3 -m pip install paramiko)
"""
import ctypes
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
OCD_DIR = "/home/{user}/r8ocd"

# ------------------------------------------------------------------ languages
LANGS = {"zh-TW": "繁體中文", "en": "English", "ja": "日本語"}
STR = {
    # window / fields
    "title":        {"zh-TW": "CR8 Debug - RZ/V2H 自主式除錯器", "en": "CR8 Debug - RZ/V2H self-hosted debugger", "ja": "CR8 Debug - RZ/V2H セルフホスト・デバッガ"},
    "lang":         {"zh-TW": "語言", "en": "Language", "ja": "言語"},
    "host":         {"zh-TW": "板子位址（IP）", "en": "Board address (IP)", "ja": "ボードのアドレス (IP)"},
    "user":         {"zh-TW": "帳號", "en": "User", "ja": "ユーザー名"},
    "password":     {"zh-TW": "密碼", "en": "Password", "ja": "パスワード"},
    "remember":     {"zh-TW": "記住密碼（存在 %APPDATA%\\cr8-debug，只有你這個 Windows 帳號讀得到）",
                     "en": "Remember the password (kept in %APPDATA%\\cr8-debug, readable only by your Windows account)",
                     "ja": "パスワードを記憶する（%APPDATA%\\cr8-debug に保存、この Windows アカウントのみ読み取り可）"},
    "fw":           {"zh-TW": "core0 韌體檔名（板上）", "en": "core0 firmware (name on the board)", "ja": "core0 ファームウェア（ボード上の名前）"},
    "project_dir":  {"zh-TW": "core0 e² studio 專案", "en": "core0 e² studio project", "ja": "core0 e² studio プロジェクト"},
    "fw1":          {"zh-TW": "core1 韌體檔名（板上）", "en": "core1 firmware (name on the board)", "ja": "core1 ファームウェア（ボード上の名前）"},
    "project1_dir": {"zh-TW": "core1 e² studio 專案（可留空）", "en": "core1 e² studio project (optional)", "ja": "core1 e² studio プロジェクト（省略可）"},
    "e2studio":     {"zh-TW": "e² studio 安裝目錄", "en": "e² studio install folder", "ja": "e² studio インストール先"},
    "workspace":    {"zh-TW": "e² studio 工作區", "en": "e² studio workspace", "ja": "e² studio ワークスペース"},
    "auto_stop":    {"zh-TW": "關掉 e² studio 時自動收尾（resume 兩核、停 OpenOCD、斷線）",
                     "en": "When e² studio closes: resume both cores, stop OpenOCD, disconnect",
                     "ja": "e² studio 終了時に自動で後始末（両コア resume、OpenOCD 停止、切断）"},
    # buttons
    "btn_go":       {"zh-TW": "連線並開始除錯", "en": "Connect & Debug", "ja": "接続してデバッグ開始"},
    "btn_redeploy": {"zh-TW": "重新部署韌體（core0+core1）", "en": "Redeploy firmware (core0+core1)", "ja": "ファームウェア再配置 (core0+core1)"},
    "btn_stop":     {"zh-TW": "收尾 / 停止", "en": "Stop", "ja": "停止"},
    "btn_install":  {"zh-TW": "安裝到板子", "en": "Install on board", "ja": "ボードにインストール"},
    # status line
    "st_ready":     {"zh-TW": "就緒", "en": "ready", "ja": "準備完了"},
    "st_working":   {"zh-TW": "處理中 ...", "en": "working ...", "ja": "処理中 ..."},
    "st_closing":   {"zh-TW": "關閉中：正在停止板上的 OpenOCD ...", "en": "closing: stopping OpenOCD on the board ...", "ja": "終了中：ボード上の OpenOCD を停止しています ..."},
    "busy":         {"zh-TW": "忙碌中，請等目前這一步完成", "en": "busy - wait for the current step to finish", "ja": "処理中です。現在のステップが終わるまでお待ちください"},
    "ok":           {"zh-TW": "完成", "en": "ok", "ja": "完了"},
    "error":        {"zh-TW": "錯誤：{msg}", "en": "ERROR: {msg}", "ja": "エラー：{msg}"},
    "need_host":    {"zh-TW": "板子位址和帳號必填", "en": "Board address and user are required", "ja": "ボードのアドレスとユーザー名は必須です"},
    # connection
    "connecting":   {"zh-TW": "連線到 {user}@{host} ...", "en": "connecting to {user}@{host} ...", "ja": "{user}@{host} に接続中 ..."},
    "logged_in":    {"zh-TW": "已登入", "en": "logged in", "ja": "ログインしました"},
    "login_failed": {"zh-TW": "登入失敗：請檢查帳號與密碼", "en": "login failed: check the user name and password", "ja": "ログイン失敗：ユーザー名とパスワードを確認してください"},
    "unreachable":  {"zh-TW": "連不到 {host}：{err}", "en": "cannot reach {host}: {err}", "ja": "{host} に到達できません：{err}"},
    "sudo_needs_pw": {"zh-TW": "用金鑰登入成功，但板上的 sudo 需要密碼：請填密碼欄",
                      "en": "logged in with an SSH key, but sudo on the board needs the password: fill in the password field",
                      "ja": "SSH 鍵でログインできましたが、ボードの sudo にはパスワードが必要です：パスワード欄を入力してください"},
    "sudo_refused": {"zh-TW": "板上的 sudo 拒絕了這個密碼", "en": "sudo refused the password on the board", "ja": "ボードの sudo がパスワードを拒否しました"},
    "disconnected": {"zh-TW": "已斷線", "en": "disconnected", "ja": "切断しました"},
    "nothing_stop": {"zh-TW": "沒有東西需要收尾", "en": "nothing to stop", "ja": "停止するものはありません"},
    # install
    "not_installed": {"zh-TW": "板子還沒安裝除錯工具 -> 安裝（只做一次）", "en": "board not set up yet -> installing (once)", "ja": "ボードは未セットアップ -> インストールします（初回のみ）"},
    "up_pkg":       {"zh-TW": "上傳 A55 端套件到 ~/cr8-install ...", "en": "uploading the A55-side package to ~/cr8-install ...", "ja": "A55 側パッケージを ~/cr8-install へアップロード中 ..."},
    "up_ocd":       {"zh-TW": "上傳預建的 OpenOCD（{mb} MB）...", "en": "uploading the prebuilt OpenOCD ({mb} MB) ...", "ja": "ビルド済み OpenOCD（{mb} MB）をアップロード中 ..."},
    "no_tarball":   {"zh-TW": "倉庫的 debug/ 或 .release/ 沒有 openocd-rzv2h-aarch64.tar.gz：板子會自己編譯（約 10 分鐘）",
                     "en": "no openocd-rzv2h-aarch64.tar.gz in the repo's debug/ or .release/: the board builds it (~10 min)",
                     "ja": "リポジトリの debug/ または .release/ に openocd-rzv2h-aarch64.tar.gz がありません：ボード上でビルドします（約 10 分）"},
    "run_install":  {"zh-TW": "在板上執行 install-on-evk.sh（以 root 執行、HOME 保留）...", "en": "running install-on-evk.sh on the board (as root, HOME kept) ...", "ja": "ボード上で install-on-evk.sh を実行中（root、HOME は維持）..."},
    "install_failed": {"zh-TW": "install-on-evk.sh 失敗（見 log）", "en": "install-on-evk.sh failed (see log)", "ja": "install-on-evk.sh が失敗しました（ログ参照）"},
    "inst_core1":   {"zh-TW": "已安裝 core1 韌體 {fw}", "en": "installed core1 firmware {fw}", "ja": "core1 ファームウェア {fw} をインストールしました"},
    "inst_local":   {"zh-TW": "已安裝本機建置的 ELF；下次（重）啟動才會載入 -> 按「重新部署」立即執行",
                     "en": "installed the ELF(s) built here; loaded on the next (re)start -> press Redeploy to run them now",
                     "ja": "このPCでビルドした ELF をインストールしました。次回（再）起動時に読み込まれます -> 今すぐ実行するには「再配置」を押してください"},
    # firmware / cores
    "core_running": {"zh-TW": "CR8 core{n} 執行中（{fw}）", "en": "CR8 core{n} running ({fw})", "ja": "CR8 core{n} 実行中（{fw}）"},
    "core_start":   {"zh-TW": "CR8 core{n} 狀態是「{st}」-> 啟動 {fw}", "en": "CR8 core{n} is '{st}' -> starting {fw}", "ja": "CR8 core{n} は「{st}」-> {fw} を起動します"},
    "pair_restart": {"zh-TW": "整對重啟：core0 {fw} + core1 {fw1}（CR8 沒有單核 reset）", "en": "restarting the pair: core0 {fw} + core1 {fw1} (no per-core reset on the CR8)", "ja": "ペアを再起動：core0 {fw} + core1 {fw1}（CR8 にはコア単位のリセットがありません）"},
    "core_failed":  {"zh-TW": "CR8 core{n} 沒有起來（見 log）", "en": "CR8 core{n} did not come up (see log)", "ja": "CR8 core{n} が起動しませんでした（ログ参照）"},
    "core1_skip":   {"zh-TW": "core1 沒起來；core0 仍可除錯（core1 的 session 會沒東西可接）", "en": "core1 did not start; core0 debugging still works (the core1 session will have nothing to attach to)", "ja": "core1 は起動しませんでした。core0 のデバッグは可能です（core1 セッションは接続先なし）"},
    "bb_fault":     {"zh-TW": "!! core{n} 黑盒子：fault_type {v}（{name}）-> 該核停在 abort handler；按「重新部署」整對重啟",
                     "en": "!! core{n} black box: fault_type {v} ({name}) -> the core is in its abort handler; press Redeploy to restart the pair",
                     "ja": "!! core{n} ブラックボックス：fault_type {v}（{name}）-> コアは abort handler で停止中。「再配置」でペアを再起動してください"},
    "bb_abort":     {"zh-TW": "有一顆 CR8 停在 abort handler：先按「重新部署」（整對重啟），再連線一次",
                     "en": "a CR8 core is sitting in its abort handler: press Redeploy (restarts the pair), then Connect again",
                     "ja": "CR8 コアが abort handler で停止しています：「再配置」（ペア再起動）後、もう一度接続してください"},
    "fault_names":  {"zh-TW": {1: "reset", 2: "未定義指令", 3: "prefetch abort", 4: "data abort", 5: "未定義指令", 6: "FreeRTOS assert", 7: "堆疊溢位", 8: "malloc 失敗"},
                     "en": {1: "reset", 2: "undefined instruction", 3: "prefetch abort", 4: "data abort", 5: "undefined instruction", 6: "FreeRTOS assert", 7: "stack overflow", 8: "malloc failed"},
                     "ja": {1: "リセット", 2: "未定義命令", 3: "prefetch abort", 4: "data abort", 5: "未定義命令", 6: "FreeRTOS assert", 7: "スタックオーバーフロー", 8: "malloc 失敗"}},
    "unknown":      {"zh-TW": "未知", "en": "unknown", "ja": "不明"},
    # OpenOCD
    "ocd_already":  {"zh-TW": "OpenOCD 已在執行", "en": "OpenOCD already running", "ja": "OpenOCD は既に実行中です"},
    "gate_closed":  {"zh-TW": "CR8 除錯匯流排未就緒（CPG_LP_CR8_CTL3 bit12=0）：CR8 啟動了嗎？MD_BOOT3（EVK DSW1-7）是否 ON？",
                     "en": "CR8 debug APB not ready (CPG_LP_CR8_CTL3 bit12=0): is the CR8 started? MD_BOOT3 (EVK DSW1-7) ON?",
                     "ja": "CR8 デバッグ APB が未準備（CPG_LP_CR8_CTL3 bit12=0）：CR8 は起動済みですか？MD_BOOT3（EVK DSW1-7）は ON ですか？"},
    "ocd_started":  {"zh-TW": "OpenOCD 已啟動（Examination succeed）", "en": "OpenOCD started (Examination succeed)", "ja": "OpenOCD を起動しました（Examination succeed）"},
    "ocd_failed":   {"zh-TW": "OpenOCD 啟動失敗：\n{log}", "en": "OpenOCD failed to start:\n{log}", "ja": "OpenOCD の起動に失敗しました：\n{log}"},
    "ocd_nolisten": {"zh-TW": "OpenOCD 沒有開始監聽", "en": "OpenOCD did not start listening", "ja": "OpenOCD が待ち受けを開始しませんでした"},
    "ocd_stopping": {"zh-TW": "停止 OpenOCD（resume 所有核心、shutdown）", "en": "stopping OpenOCD (resume all cores, shutdown)", "ja": "OpenOCD を停止します（全コア resume、shutdown）"},
    "ports_open":   {"zh-TW": "gdb 埠已開在這台 PC：{p0}（core0）、{p1}（core1）", "en": "gdb ports open on this PC: {p0} (core0), {p1} (core1)", "ja": "この PC で gdb ポートを開きました：{p0}（core0）、{p1}（core1）"},
    "fwd_err":      {"zh-TW": "轉發 {port}：{err}", "en": "forward {port}: {err}", "ja": "転送 {port}：{err}"},
    # redeploy
    "uploading":    {"zh-TW": "上傳 {name} ...", "en": "uploading {name} ...", "ja": "{name} をアップロード中 ..."},
    "install_fw_failed": {"zh-TW": "韌體安裝失敗：{out}", "en": "could not install the firmware: {out}", "ja": "ファームウェアをインストールできませんでした：{out}"},
    "redeployed":   {"zh-TW": "已重新部署；回 e² studio 再按一次 Debug", "en": "redeployed; press Debug again in e² studio", "ja": "再配置しました。e² studio でもう一度 Debug を押してください"},
    "elf_age":      {"zh-TW": "core{n} 的 ELF 建置於 {m} 分 {s} 秒前", "en": "core{n} ELF built {m} min {s} s ago", "ja": "core{n} の ELF は {m} 分 {s} 秒前にビルド"},
    "elf_missing":  {"zh-TW": "找不到 ELF：{path}\n請先在 e² studio 建置：Project -> Build Project（Ctrl+B）",
                     "en": "ELF not found: {path}\nBuild first: Project -> Build Project (Ctrl+B) in e² studio",
                     "ja": "ELF が見つかりません：{path}\n先に e² studio でビルドしてください：Project -> Build Project（Ctrl+B）"},
    "tool_failed":  {"zh-TW": "{tool} 失敗：\n{out}", "en": "{tool} failed:\n{out}", "ja": "{tool} が失敗しました：\n{out}"},
    # e2 studio / workspace
    "e2s_missing":  {"zh-TW": "找不到 e² studio：{exe}", "en": "e² studio not found: {exe}", "ja": "e² studio が見つかりません：{exe}"},
    "ws_locked":    {"zh-TW": "工作區 {ws} 使用中（e² studio 開著？）且缺少 {names}：請關閉 e² studio 再試",
                     "en": "workspace {ws} is in use (e² studio open?) and lacks {names}: close e² studio and retry",
                     "ja": "ワークスペース {ws} は使用中（e² studio 起動中？）で {names} がありません：e² studio を閉じて再試行してください"},
    "ws_import":    {"zh-TW": "工作區缺少 {names} -> 匯入中（無頭 e² studio，約 30 秒）", "en": "workspace lacks {names} -> importing (headless e² studio, ~30 s)", "ja": "ワークスペースに {names} がありません -> インポート中（ヘッドレス e² studio、約 30 秒）"},
    "ws_import_failed": {"zh-TW": "無頭匯入沒有登錄 {names}：{out}", "en": "headless import did not register {names}: {out}", "ja": "ヘッドレスインポートで {names} が登録されませんでした：{out}"},
    "ws_imported":  {"zh-TW": "專案已匯入工作區", "en": "project(s) imported into the workspace", "ja": "プロジェクトをワークスペースにインポートしました"},
    "e2s_start":    {"zh-TW": "啟動 e² studio ... Run -> Debug Configurations -> GDB Hardware Debugging -> {names}",
                     "en": "starting e² studio ... Run -> Debug Configurations -> GDB Hardware Debugging -> {names}",
                     "ja": "e² studio を起動中 ... Run -> Debug Configurations -> GDB Hardware Debugging -> {names}"},
    "e2s_closed":   {"zh-TW": "e² studio 已關閉 -> 收尾", "en": "e² studio closed -> stopping", "ja": "e² studio が終了 -> 後始末します"},
    "core_states":  {"zh-TW": "CR8 core0：{s0}，core1：{s1}", "en": "CR8 core0: {s0}, core1: {s1}", "ja": "CR8 core0：{s0}、core1：{s1}"},
    "stop_failed":  {"zh-TW": "收尾失敗：{err}", "en": "stop failed: {err}", "ja": "停止に失敗しました：{err}"},
}
LANG = "en"


def T(key, **kw):
    """translated string for the current language (English as fallback)"""
    entry = STR[key]
    s = entry.get(LANG, entry["en"])
    return s.format(**kw) if kw else s


def default_lang():
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF   # primary language id
    except (AttributeError, OSError):
        return "en"
    return {0x04: "zh-TW", 0x11: "ja"}.get(lid, "en")


def find_tarball():
    for d in ("debug", ".release"):
        p = os.path.join(REPO, d, "openocd-rzv2h-aarch64.tar.gz")
        if os.path.isfile(p):
            return p
    return None


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
    "lang": "",            # "" = follow the Windows display language
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
        json.dump(out, f, indent=2, ensure_ascii=False)


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
                raise RuntimeError(T("sudo_needs_pw"))
            if self.run("true", sudo=True)[0] != 0:
                raise RuntimeError(T("sudo_refused"))

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

    def check_blackboxes(self):
        """read fault_type (+0x44) of both black boxes; log and return the cores that captured a fault"""
        out = self.run("for bb in 0x439F0044 0x441F0044; do busybox devmem $bb 32 2>/dev/null || echo 0; done", sudo=True)[1].split()
        bad = []
        names = STR["fault_names"].get(LANG, STR["fault_names"]["en"])
        for core, word in enumerate(out[:2]):
            try:
                v = int(word, 16)
            except ValueError:
                continue
            if v not in (0, 0xFFFFFFFF):
                bad.append(core)
                self.log(T("bb_fault", n=core, v=v, name=names.get(v, T("unknown"))))
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
        self.log(T("up_pkg"))
        self.run("rm -rf ~/cr8-install && mkdir -p ~/cr8-install/debug ~/cr8-install/firmware/tools/board ~/cr8-install/examples/demo_servo")
        self.put_tree(os.path.join(REPO, "debug"), "cr8-install/debug")            # sftp paths: relative to $HOME
        self.put_tree(os.path.join(REPO, "firmware", "tools", "board"), "cr8-install/firmware/tools/board")
        if fw_elf and os.path.isfile(fw_elf):
            self.put(fw_elf, "cr8-install/examples/demo_servo/cr8_demo.elf")
        if tarball and os.path.isfile(tarball):
            self.log(T("up_ocd", mb=os.path.getsize(tarball) // 1000000))
            self.put(tarball, "cr8-install/debug/openocd-rzv2h-aarch64.tar.gz")
        else:
            self.log(T("no_tarball"))
        self.log(T("run_install"))
        # The script calls sudo itself and installs into $HOME/r8ocd; without a tty the sudo
        # timestamp cannot be shared, so run the whole script as root with HOME pointed at the
        # user and hand the result back to the user afterwards.
        rc, out = self.run(f"chmod +x {home}/cr8-install/debug/*.sh {home}/cr8-install/firmware/tools/board/*.sh; "
                           f"cd {home}/cr8-install && HOME={home} bash debug/install-on-evk.sh; rc=$?; "
                           f"chown -R {self.user}: {home}/r8ocd {home}/cr8-install; exit $rc", sudo=True, timeout=1500)
        for line in out.splitlines()[-14:]:
            self.log("  " + line)
        if rc != 0:
            raise RuntimeError(T("install_failed"))

    def start_cr8(self, fw, fw1=None):
        """(re)start core0 with fw (and core1 with fw1 when given). The CR8 cluster has no
        per-core reset: when the other core is running a single-core restart is refused by the
        board scripts, so both cores go down and up again (restart-r8-pair.sh).
        Never call this while OpenOCD runs."""
        core1_state, core1_fw = (self.run("cat /sys/class/remoteproc/remoteproc2/state /sys/class/remoteproc/remoteproc2/firmware")[1].split() + ["none", ""])[:2]
        if fw1 or core1_state == "running":
            fw1 = fw1 or core1_fw
            self.log(T("pair_restart", fw=fw, fw1=fw1))
            rc, out = self.run(f"{self.ocd}/board/restart-r8-pair.sh {fw} {fw1}", sudo=True, timeout=120)
            want1 = True
        else:
            rc, out = self.run(f"{self.ocd}/board/start-cr8.sh {fw}", sudo=True, timeout=90)
            want1 = False
        for line in out.splitlines()[-4:]:
            self.log("  " + line)
        if self.core0_state() != "running" or (not want1 and rc != 0):
            raise RuntimeError(T("core_failed", n=0))
        if want1 and self.core1_state() != "running":
            raise RuntimeError(T("core_failed", n=1))

    def start_firmware(self, fw, fw1=None):
        """make sure core0 runs (start fw if offline); then core1 if fw1 is given and installed"""
        st = self.core0_state()
        if st == "running":
            self.log(T("core_running", n=0, fw=self.run("cat /sys/class/remoteproc/remoteproc1/firmware")[1]))
        else:
            self.log(T("core_start", n=0, st=st, fw=fw))
            self.start_cr8(fw)
        st1 = self.core1_state()
        if st1 == "running":
            self.log(T("core_running", n=1, fw=self.run("cat /sys/class/remoteproc/remoteproc2/firmware")[1]))
        elif fw1 and st1 != "none" and self.run(f"test -f /lib/firmware/{fw1}")[0] == 0:
            self.log(T("core_start", n=1, st=st1, fw=fw1))
            rc, out = self.run(f"{self.ocd}/board/start-cr8-core1.sh {fw1}", sudo=True, timeout=90)
            for line in out.splitlines()[-3:]:
                self.log("  " + line)
            if self.core1_state() != "running":
                self.log(T("core1_skip"))

    def start_openocd(self):
        if self.ocd_running():
            self.log(T("ocd_already"))
            return
        if not self.debug_gate_open():
            raise RuntimeError(T("gate_closed"))
        self.run(f"cd {self.ocd} && : > ocd.log && nohup ./r8ocd.sh >> ocd.log 2>&1 &", sudo=True, timeout=20)
        for _ in range(30):
            time.sleep(1)
            _, log = self.run(f"grep -v '^Debug' {self.ocd}/ocd.log | tail -20")
            if "Listening on port 3333" in log and self.ocd_running():
                self.log(T("ocd_started"))
                return
            if "Refusing" in log or "Error" in log or "not found" in log:
                raise RuntimeError(T("ocd_failed", log=log))
        raise RuntimeError(T("ocd_nolisten"))

    def stop_openocd(self):
        if not self.ocd_running():
            return
        self.log(T("ocd_stopping"))
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
            self.log(T("uploading", name=name))
            self.put(elf, f"/tmp/{name}")
            rc, out = self.run(f"install -m 644 /tmp/{name} /lib/firmware/{name}", sudo=True)
            if rc != 0:
                raise RuntimeError(T("install_fw_failed", out=out))
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
                self.log(T("fwd_err", port=self.port, err=e))
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
    names = ", ".join(n for _, n in missing)
    if os.path.isfile(os.path.join(ws, ".metadata", ".lock")):
        try:
            os.remove(os.path.join(ws, ".metadata", ".lock"))   # stale lock from a closed e2 studio
        except OSError:
            raise RuntimeError(T("ws_locked", ws=ws, names=names)) from None
    exe = os.path.join(cfg["e2studio"], "eclipse", "e2studioc.exe")
    log(T("ws_import", names=names))
    os.makedirs(ws, exist_ok=True)
    args = [exe, "-nosplash", "-data", ws, "-application", "org.eclipse.cdt.managedbuilder.core.headlessbuild",
            "-import", os.path.join(REPO, "firmware", "cm33_demo")]
    for pdir, _ in missing:
        args += ["-import", pdir]
    r = subprocess.run(args + ["-no-indexer"], capture_output=True, text=True, timeout=600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    still = [n for _, n in missing if not os.path.isdir(os.path.join(meta, n))]
    if still:
        raise RuntimeError(T("ws_import_failed", names=", ".join(still), out=(r.stdout + r.stderr)[-800:]))
    log(T("ws_imported"))


def patch_elf(cfg, log, core=0):
    """post-process a copy of the ELF e2 studio built (zero-size DDR PT_LOADs -> PT_NULL;
    core1 additionally nulls the 4-byte PT_LOAD at 0x081BFFFC, as build.ps1 does)"""
    pdir = cfg["project_dir"] if core == 0 else cfg["project1_dir"]
    fw = cfg["fw"] if core == 0 else cfg["fw1"]
    src = os.path.join(pdir, "Debug", PROJ + ".elf")      # the artifact keeps the core0 name in both projects
    if not os.path.isfile(src):
        raise RuntimeError(T("elf_missing", path=src))
    age = int(time.time() - os.path.getmtime(src))
    log(T("elf_age", n=core, m=age // 60, s=age % 60))
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
            raise RuntimeError(T("tool_failed", tool=os.path.basename(cmd[1]), out=r.stdout + r.stderr))
    return dst


def have_elf(cfg, core):
    pdir = cfg["project_dir"] if core == 0 else cfg.get("project1_dir", "")
    return bool(pdir) and os.path.isfile(os.path.join(pdir, "Debug", PROJ + ".elf"))


# ------------------------------------------------------------------ GUI
class App(tk.Tk):
    FIELDS = (("host", {}), ("user", {}), ("password", {"show": "*"}), ("remember", None),
              ("fw", {}), ("project_dir", {"browse": True}), ("fw1", {}), ("project1_dir", {"browse": True}),
              ("e2studio", {"browse": True}), ("workspace", {"browse": True}), ("auto_stop", None))

    def __init__(self):
        global LANG
        super().__init__()
        self.cfg = load_config()
        LANG = self.cfg.get("lang") or default_lang()
        if LANG not in LANGS:
            LANG = "en"
        self.resizable(True, True)
        self.evk = None
        self.e2s = None
        self.q = queue.Queue()
        self.busy = False
        self.frame = None
        self.values = {k: self.cfg.get(k, "") for k, _ in self.FIELDS}
        self.lines = []            # log lines, kept across a language switch
        self._build()
        self.after(100, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        """(re)create every widget in the current language; entry values and the log are kept"""
        if self.frame is not None:
            self.frame.destroy()
        self.title(T("title"))
        f = ttk.Frame(self, padding=10)
        f.grid(sticky="nsew")
        self.frame = f
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.v = {}

        # language box, top right
        top = ttk.Frame(f)
        top.grid(row=0, column=0, columnspan=3, sticky="e")
        ttk.Label(top, text=T("lang")).pack(side="left", padx=4)
        self.lang_var = tk.StringVar(value=LANGS[LANG])
        box = ttk.Combobox(top, textvariable=self.lang_var, values=list(LANGS.values()), state="readonly", width=10)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", self._switch_lang)

        r = 1
        for key, opt in self.FIELDS:
            if opt is None:                       # checkbox
                var = tk.BooleanVar(value=bool(self.values.get(key)))
                ttk.Checkbutton(f, text=T(key), variable=var).grid(row=r, column=1, sticky="w")
            else:
                ttk.Label(f, text=T(key)).grid(row=r, column=0, sticky="w", pady=2)
                var = tk.StringVar(value=str(self.values.get(key, "")))
                ttk.Entry(f, textvariable=var, width=44, show=opt.get("show")).grid(row=r, column=1, sticky="we", pady=2)
                if opt.get("browse"):
                    ttk.Button(f, text="...", width=3, command=lambda v=var: self._browse(v)).grid(row=r, column=2, padx=2)
            self.v[key] = var
            r += 1

        b = ttk.Frame(f)
        b.grid(row=r, column=0, columnspan=3, pady=8, sticky="w")
        self.btn_go = ttk.Button(b, text=T("btn_go"), command=self.go)
        self.btn_go.pack(side="left", padx=3)
        self.btn_redeploy = ttk.Button(b, text=T("btn_redeploy"), command=self.redeploy)
        self.btn_redeploy.pack(side="left", padx=3)
        self.btn_stop = ttk.Button(b, text=T("btn_stop"), command=self.stop)
        self.btn_stop.pack(side="left", padx=3)
        self.btn_install = ttk.Button(b, text=T("btn_install"), command=self.install)
        self.btn_install.pack(side="left", padx=3)
        r += 1

        self.txt = tk.Text(f, height=16, width=96, state="disabled", font=("Consolas", 9))
        self.txt.grid(row=r, column=0, columnspan=3, sticky="nsew")
        f.rowconfigure(r, weight=1)
        f.columnconfigure(1, weight=1)
        r += 1
        self.status = tk.StringVar(value=T("st_ready") if not self.busy else T("st_working"))
        ttk.Label(f, textvariable=self.status).grid(row=r, column=0, columnspan=3, sticky="w")
        for line in self.lines:
            self._append(line)

    def _switch_lang(self, _event=None):
        global LANG
        code = next((c for c, n in LANGS.items() if n == self.lang_var.get()), "en")
        if code == LANG:
            return
        for k, var in self.v.items():          # keep what the user typed
            self.values[k] = var.get()
        LANG = code
        self.cfg["lang"] = code
        save_config({**self.cfg, **self.values})
        self._build()

    def _browse(self, var):
        p = filedialog.askdirectory(initialdir=var.get() or os.path.expanduser("~"))
        if p:
            var.set(p.replace("/", "\\"))

    # -- logging from worker threads --------------------------------------
    def log(self, msg):
        self.q.put(msg)

    def _append(self, line):
        self.txt.configure(state="normal")
        self.txt.insert("end", line + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if isinstance(msg, tuple):
                    if msg[0] == "quit":
                        self.destroy()
                        return
                    self.log(T("e2s_closed"))
                    self.stop()
                    continue
                line = time.strftime("%H:%M:%S ") + msg
                self.lines.append(line)
                self._append(line)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _collect(self):
        for k, var in self.v.items():
            self.cfg[k] = var.get()
            self.values[k] = var.get()
        self.cfg["lang"] = LANG
        save_config(self.cfg)
        if not self.cfg["host"] or not self.cfg["user"]:
            raise RuntimeError(T("need_host"))

    def _work(self, fn, done=None):
        if self.busy:
            messagebox.showinfo("CR8 Debug", T("busy"))
            return
        self.busy = True
        self.status.set(T("st_working"))

        def runner():
            try:
                fn()
                self.q.put(T("ok"))
                if done:
                    done()
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self.q.put(T("error", msg=msg))
                self.after(0, lambda: messagebox.showerror("CR8 Debug", msg))
            finally:
                self.busy = False
                self.after(0, lambda: self.status.set(T("st_ready")))
        threading.Thread(target=runner, daemon=True).start()

    def _connect(self):
        if self.evk:
            try:
                self.evk.run("true")
                return
            except Exception:  # noqa: BLE001
                self.evk = None
        self.log(T("connecting", user=self.cfg["user"], host=self.cfg["host"]))
        try:
            self.evk = Evk(self.cfg["host"], self.cfg["user"], self.cfg["password"], self.log)
        except paramiko.AuthenticationException:
            raise RuntimeError(T("login_failed")) from None
        except (socket.error, paramiko.SSHException) as e:
            raise RuntimeError(T("unreachable", host=self.cfg["host"], err=e)) from None
        self.log(T("logged_in"))

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
                self.log(T("not_installed"))
                self.evk.install(DEMO_ELF, find_tarball())
            self.evk.start_firmware(self.cfg["fw"], self.cfg.get("fw1") or None)
            if self.evk.check_blackboxes():
                raise RuntimeError(T("bb_abort"))
            self.evk.start_openocd()
            for p in PORTS:
                self.evk.forward(p)
            self.log(T("ports_open", p0=PORTS[0], p1=PORTS[1]))
            prepare_launch(self.cfg)
            exe = os.path.join(self.cfg["e2studio"], "eclipse", "e2studio.exe")
            if not os.path.isfile(exe):
                raise RuntimeError(T("e2s_missing", exe=exe))
            ensure_workspace(self.cfg, self.log)
            names = " / ".join(f"'{LAUNCH[c][:-7]}'" for c, _, _, _ in projects(self.cfg))
            self.log(T("e2s_start", names=names))
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
                self.log(T("core_states", s0=self.evk.core0_state(), s1=self.evk.core1_state()))
                self.evk.check_blackboxes()
                self.evk.close()
                self.evk = None
                self.log(T("disconnected"))
            else:
                self.log(T("nothing_stop"))
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
            self.log(T("redeployed"))
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
                self.log(T("inst_core1", fw=self.cfg["fw1"]))
            if elf != DEMO_ELF:
                self.log(T("inst_local"))
        self._work(work)

    def _on_close(self):
        """closing the window = Stop: resume the cores, shut OpenOCD down, disconnect, then exit.
        e2 studio (if still open) is left alone; its gdb session just reports a disconnect."""
        if not self.evk:
            self.destroy()
            return
        self.status.set(T("st_closing"))
        for b in (self.btn_go, self.btn_redeploy, self.btn_stop, self.btn_install):
            b.configure(state="disabled")

        def work():
            try:
                self.evk.stop_openocd()
                self.log(T("core_states", s0=self.evk.core0_state(), s1=self.evk.core1_state()))
            except Exception as e:  # noqa: BLE001
                self.log(T("stop_failed", err=e))
            finally:
                try:
                    self.evk.close()
                finally:
                    self.q.put(("quit",))
        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
