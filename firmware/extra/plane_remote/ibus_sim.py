#!/usr/bin/env python3
"""i-BUS frame simulator for testing plane_remote without a receiver.
Creates a pty, prints its slave path (pass it to server.py --ibus-dev), then streams 32-byte
FlySky i-BUS servo frames at ~140 Hz.  Channel values come from a JSON file re-read every frame
(default /tmp/ibus_sim.json: {"ch":[1500,1500,1000,1500,1000,...]}); if the file says {"stop":1}
the stream pauses (link-loss test).
usage: ibus_sim.py [ctrl.json]
"""
import json
import os
import sys
import time

ctrl = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ibus_sim.json"
m, s = os.openpty()
print(os.ttyname(s), flush=True)
ch = [1500, 1500, 1000, 1500, 1000, 1000] + [1500] * 8
while True:
    try:
        j = json.load(open(ctrl))
        if j.get("ch"):
            ch = (list(j["ch"]) + [1500] * 14)[:14]
        stop = j.get("stop", 0)
    except Exception:
        stop = 0
    if not stop:
        f = bytearray([0x20, 0x40])
        for v in ch:
            f += int(v).to_bytes(2, "little")
        c = (0xFFFF - sum(f)) & 0xFFFF
        f += c.to_bytes(2, "little")
        os.write(m, bytes(f))
    time.sleep(0.007)
