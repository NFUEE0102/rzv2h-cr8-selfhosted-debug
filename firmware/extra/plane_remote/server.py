#!/usr/bin/env python3
"""plane_remote — web / gamepad remote for the EVK fixed-wing bench (core0-pwm-plane firmware).

Runs on the A55 as root (r8_bench needs /dev/mem).  Keeps ONE `r8_bench pwmd` alive as the
single rpmsg client and feeds it "<gpt> <a|b> 50 <permille>" lines.

Channels (Pmod CN2, see variants/core0_pwm_plane.py):
    motor  GPT4.A  P74  CN2-7
    left   GPT4.B  P75  CN2-8      left wing surface
    right  GPT7.A  PA6  CN2-9      right wing surface
    tail   GPT6.A  PA4  CN2-10     horizontal tail

Mixer (all inputs -1..+1, throttle 0..1):
    left  = +roll*ail_l + pitch*elevon
    right = -roll*ail_r + pitch*elevon
    tail  =  pitch
    -> per-channel reverse, trim (us), end points; motor 1000..2000 us only when armed,
       forced-low (duty 0) when disarmed.
Safety: if the browser stops sending setpoints for WATCHDOG_S the motor is cut (duty 0) and the
surfaces are centred; the arm switch is dropped.

usage: server.py [--port 8090] [--r8bench /home/ubuntu/r8_bench/r8_bench] [--dry]
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHDOG_S = 1.0
RATE_HZ = 50
CH = {  # name -> (gpt, a|b)
    "motor": (4, "a"),
    "left": (4, "b"),
    "right": (7, "a"),
    "tail": (6, "a"),
}
DEFAULT_CFG = {
    "ail_l": 1.0, "ail_r": 1.0, "elevon": 0.0, "pitch_gain": 1.0,
    "rev": {"left": False, "right": False, "tail": False},
    "trim": {"left": 0, "right": 0, "tail": 0},          # us
    "min_us": 1000, "max_us": 2000, "centre_us": 1500, "throw_us": 400,
    "motor_min_us": 1000, "motor_max_us": 2000,
}

DEFAULT_RC = {   # FlySky FS-iA6B i-BUS on /dev/ttySC1 (EVK Pmod CN1 pin 8 = P85 RX), AETR order
    "enabled": True, "dev": "/dev/ttySC1",
    "map": {"roll": 0, "pitch": 1, "throttle": 2, "arm": 4},   # 0-based i-BUS channel index
    "rev": {"roll": False, "pitch": False, "throttle": False},
    "arm_threshold_us": 1500, "throttle_arm_max_us": 1100, "link_timeout_s": 0.5,
}
RC_LINK_S = 0.5

state = {
    "roll": 0.0, "pitch": 0.0, "throttle": 0.0, "armed": False,
    "cfg": json.loads(json.dumps(DEFAULT_CFG)),
    "last_rx": 0.0, "watchdog_tripped": False,
    "out_us": {"motor": 0, "left": 1500, "right": 1500, "tail": 1500},
    "pwmd_alive": False, "sent": 0, "r8_status": None, "r8_seq": 0,
    "rc": {"cfg": json.loads(json.dumps(DEFAULT_RC)), "ch": [0] * 14, "frames": 0, "bad": 0,
           "last_frame": 0.0, "link": False, "active": False, "arm_latch": False, "failsafe": 0,
           "dev_open": False},
}
lock = threading.Lock()


def ibus_reader(dev):
    """read FlySky i-BUS servo frames (32 B: 20 40 | 14 x u16 LE | u16 checksum) into state['rc']"""
    import termios
    buf = b""
    fd = None
    while True:
        if fd is None:
            try:
                fd = os.open(dev, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
                t = termios.tcgetattr(fd)
                t[0] = 0                                   # iflag: raw
                t[1] = 0                                   # oflag
                t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                t[3] = 0                                   # lflag: raw
                t[4] = t[5] = termios.B115200
                t[6][termios.VMIN] = 0
                t[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, t)
                with lock:
                    state["rc"]["dev_open"] = True
            except Exception:
                with lock:
                    state["rc"]["dev_open"] = False
                fd = None
                time.sleep(2)
                continue
        try:
            d = os.read(fd, 256)
        except BlockingIOError:
            d = b""
        except OSError:
            os.close(fd)
            fd = None
            continue
        if not d:
            time.sleep(0.003)
            continue
        buf += d
        while len(buf) >= 32:
            i = buf.find(b"\x20\x40")
            if i < 0:
                buf = buf[-1:]
                break
            if i:
                buf = buf[i:]
                if len(buf) < 32:
                    break
            frame = buf[:32]
            chk = 0xFFFF - sum(frame[:30])
            if chk & 0xFFFF == frame[30] | (frame[31] << 8):
                ch = [frame[2 + 2 * k] | (frame[3 + 2 * k] << 8) for k in range(14)]
                with lock:
                    r = state["rc"]
                    r["ch"] = ch
                    r["frames"] += 1
                    r["last_frame"] = time.time()
                buf = buf[32:]
            else:
                with lock:
                    state["rc"]["bad"] += 1
                buf = buf[2:]
        if len(buf) > 512:
            buf = buf[-64:]


def rc_apply(st, now):
    """RC link owns roll/pitch/throttle/armed while frames are fresh; failsafe on loss"""
    r = st["rc"]
    c = r["cfg"]
    fresh = r["last_frame"] and (now - r["last_frame"]) < c["link_timeout_s"]
    was_link = r["link"]
    r["link"] = bool(fresh)
    if not c["enabled"]:
        r["active"] = False
        return
    if fresh:
        m, rv = c["map"], c["rev"]
        n = lambda us: clamp((us - 1500) / 500.0, -1, 1)
        roll = n(r["ch"][m["roll"]]) * (-1 if rv["roll"] else 1)
        pitch = n(r["ch"][m["pitch"]]) * (-1 if rv["pitch"] else 1)
        thr_us = r["ch"][m["throttle"]]
        thr = clamp((thr_us - 1000) / 1000.0, 0, 1)
        if rv["throttle"]:
            thr = 1 - thr
        sw = r["ch"][m["arm"]] >= c["arm_threshold_us"]
        # arm latch: switch must be seen LOW once (after boot / failsafe) and throttle low when it goes HIGH
        if not sw:
            r["arm_latch"] = True
            armed = False
        else:
            armed = st["armed"] if st["armed"] else (r["arm_latch"] and thr_us <= c["throttle_arm_max_us"])
            if armed:
                r["arm_latch"] = False
        st["roll"], st["pitch"], st["throttle"], st["armed"] = roll, pitch, thr, armed
        st["last_rx"] = now
        st["watchdog_tripped"] = False
        r["active"] = True
    elif was_link or r["active"]:
        # link just dropped: failsafe = motor off, surfaces centred, must re-arm via switch
        st["armed"] = False
        st["roll"] = st["pitch"] = st["throttle"] = 0.0
        r["active"] = False
        r["arm_latch"] = False
        r["failsafe"] += 1


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def mix(st):
    c = st["cfg"]
    roll, pitch = clamp(st["roll"], -1, 1), clamp(st["pitch"], -1, 1) * c["pitch_gain"]
    surf = {
        "left": roll * c["ail_l"] + pitch * c["elevon"],
        "right": -roll * c["ail_r"] + pitch * c["elevon"],
        "tail": pitch,
    }
    out = {}
    for k, v in surf.items():
        v = clamp(v, -1, 1) * (-1 if c["rev"][k] else 1)
        us = c["centre_us"] + v * c["throw_us"] + c["trim"][k]
        out[k] = int(round(clamp(us, c["min_us"], c["max_us"])))
    if st["armed"] and not st["watchdog_tripped"]:
        t = clamp(st["throttle"], 0, 1)
        out["motor"] = int(round(c["motor_min_us"] + t * (c["motor_max_us"] - c["motor_min_us"])))
    else:
        out["motor"] = 0          # duty 0 -> firmware forces the pin low (ESC sees no pulse)
    return out


class Pwmd:
    """one r8_bench pwmd subprocess; lines in, json report file out"""

    def __init__(self, r8bench, report, dry):
        self.r8bench, self.report, self.dry = r8bench, report, dry
        self.p = None
        self.last = {}

    def start(self):
        if self.dry:
            return
        self.p = subprocess.Popen([self.r8bench, "pwmd", self.report], stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  cwd=os.path.dirname(self.r8bench), text=True, bufsize=1)
        time.sleep(1.5)   # rpmsg endpoint bind

    def alive(self):
        return self.dry or (self.p is not None and self.p.poll() is None)

    def send(self, name, us, force=False):
        # hi-res encoding of the plane firmware: bit31 | duty in 1e-5 units (0.2 us at 50 Hz);
        # 0 = silence (forced low).  Plain permille (20 us steps) would be int(us/20).
        code = 0 if us <= 0 else (0x80000000 | int(round(us * 100000 / 20000.0)))
        if not force and self.last.get(name) == code:
            return False
        self.last[name] = code
        gpt, ab = CH[name]
        line = f"{gpt} {ab} 50 {code}\n"
        if self.dry:
            sys.stdout.write("DRY " + line)
            return True
        try:
            self.p.stdin.write(line)
            self.p.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def stop(self):
        if self.p and self.p.poll() is None:
            try:
                self.p.stdin.close()
                self.p.wait(timeout=3)
            except Exception:
                self.p.kill()


def loop(pwmd):
    period = 1.0 / RATE_HZ
    while True:
        t0 = time.time()
        with lock:
            rc_apply(state, t0)
            if state["last_rx"] and (t0 - state["last_rx"]) > WATCHDOG_S and not state["watchdog_tripped"]:
                state["watchdog_tripped"] = True
                state["armed"] = False
                state["roll"] = state["pitch"] = state["throttle"] = 0.0
            out = mix(state)
            state["out_us"] = out
            state["pwmd_alive"] = pwmd.alive()
            for name in ("motor", "left", "right", "tail"):
                if pwmd.send(name, out[name]):
                    state["sent"] += 1
            try:
                with open(pwmd.report) as f:
                    j = json.load(f)
                state["r8_status"] = 0 if j.get("ok") == 1 else j.get("status", -1)
                state["r8_seq"] = j.get("seq")
            except Exception:
                pass
        time.sleep(max(0.0, period - (time.time() - t0)))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path == "/state":
            with lock:
                self._json(state)
        else:
            self._json({"err": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json({"err": "bad json"}, 400)
        with lock:
            if self.path == "/set":                       # {roll,pitch,throttle,armed}
                if not state["rc"]["active"]:             # RC link owns the axes while alive
                    for k in ("roll", "pitch", "throttle"):
                        if k in body:
                            state[k] = float(body[k])
                    if "armed" in body:
                        state["armed"] = bool(body["armed"])
                    state["last_rx"] = time.time()
                    if state["watchdog_tripped"] and body.get("ack_watchdog"):
                        state["watchdog_tripped"] = False
                r = state["rc"]
                return self._json({"ok": True, "out_us": mix(state), "watchdog_tripped": state["watchdog_tripped"],
                                   "rc": {"link": r["link"], "active": r["active"], "ch": r["ch"][:8],
                                          "frames": r["frames"], "bad": r["bad"], "failsafe": r["failsafe"],
                                          "dev_open": r["dev_open"], "enabled": r["cfg"]["enabled"]},
                                   "axes": {"roll": state["roll"], "pitch": state["pitch"],
                                            "throttle": state["throttle"], "armed": state["armed"]}})
            if self.path == "/rc":                        # partial rc cfg update {enabled, map, rev, ...}
                for k, v in body.items():
                    if k in ("map", "rev") and isinstance(v, dict):
                        state["rc"]["cfg"][k].update(v)
                    elif k in state["rc"]["cfg"]:
                        state["rc"]["cfg"][k] = v
                if not state["rc"]["cfg"]["enabled"]:
                    state["rc"]["active"] = False
                    state["armed"] = False
                    state["throttle"] = 0.0
                return self._json({"ok": True, "rc_cfg": state["rc"]["cfg"]})
            if self.path == "/cfg":                       # partial cfg update
                for k, v in body.items():
                    if k in ("rev", "trim") and isinstance(v, dict):
                        state["cfg"][k].update(v)
                    elif k in state["cfg"]:
                        state["cfg"][k] = v
                return self._json({"ok": True, "cfg": state["cfg"]})
            if self.path == "/disarm":
                state["armed"] = False
                state["throttle"] = 0.0
                return self._json({"ok": True})
        self._json({"err": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--r8bench", default="/home/ubuntu/r8_bench/r8_bench")
    ap.add_argument("--report", default="/run/r8pwm.json")
    ap.add_argument("--dry", action="store_true", help="print pwmd lines instead of driving the R8")
    ap.add_argument("--ibus-dev", default=DEFAULT_RC["dev"], help="i-BUS serial device ('' to disable)")
    a = ap.parse_args()
    pwmd = Pwmd(a.r8bench, a.report, a.dry)
    pwmd.start()
    for name in CH:                       # explicit silent/centred start
        pwmd.send(name, mix(state)[name], force=True)
    if a.ibus_dev:
        state["rc"]["cfg"]["dev"] = a.ibus_dev
        threading.Thread(target=ibus_reader, args=(a.ibus_dev,), daemon=True).start()
    else:
        state["rc"]["cfg"]["enabled"] = False
    threading.Thread(target=loop, args=(pwmd,), daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    print(f"plane_remote on :{a.port}  pwmd={'dry' if a.dry else a.r8bench}")
    try:
        srv.serve_forever()
    finally:
        for name in CH:
            pwmd.send(name, 0, force=True)
        pwmd.stop()


if __name__ == "__main__":
    main()
