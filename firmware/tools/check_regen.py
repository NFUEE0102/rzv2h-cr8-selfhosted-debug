#!/usr/bin/env python3
"""Prove the FSP generator really regenerated a project from its configuration.xml.
e2studio caches by timestamp and can silently skip regeneration (a GTM-channel change once never
reached the generated tree and two cores ran on one tick timer). Checks after a build:
  * <gen>/vector_data.c names the GTM tick channel configured in the XML
  * <gen>/hal_data.c defines every g_gpt<N> module the XML declares
  * <gen>/pin_data.c is present when the XML has pin settings
  * the generated FSP port carries our pack patches (nesting count, tick hook, bounds check,
    barrier override, stage probes) on top of the 4.3.0 handler (lr bracket present)
The generated tree prefix is detected (RZ FSP 4.3.0 generates `rz/` next to `rzv_gen/` and `rzv_cfg/`;
`rz_gen/` / `rz_cfg/` are accepted too), so the script does not depend on the exact names.
usage: check_regen.py <project dir>
"""
import glob
import io
import os
import re
import sys

P = os.path.abspath(sys.argv[1])
x = io.open(f"{P}/configuration.xml", encoding="utf-8").read()
bad = []


def need(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        bad.append(msg)


def rd(p):
    return io.open(p, encoding="utf-8", errors="replace").read() if p and os.path.exists(p) else ""


def one(pattern, what):
    hits = sorted(glob.glob(os.path.join(P, pattern), recursive=True))
    need(len(hits) == 1, f"{what}: exactly one {pattern} in the generated tree ({len(hits)} found)")
    return hits[0] if len(hits) == 1 else None


# generated-tree prefix
GEN = next((d for d in ("rz_gen", "rzv_gen") if os.path.isdir(f"{P}/{d}")), None)
CFG = next((d for d in ("rz_cfg", "rzv_cfg") if os.path.isdir(f"{P}/{d}")), None)
FSP = next((d for d in ("rz", "rzv") if os.path.isdir(f"{P}/{d}/fsp")), None)
need(GEN is not None and CFG is not None and FSP is not None, f"generated tree present (gen={GEN} cfg={CFG} fsp={FSP})")
if bad:
    sys.exit("check_regen: no generated tree")
print(f"  info tree prefix: {FSP}/ {GEN}/ {CFG}/")

core = re.search(r'<option key="Core" value="(\w+)"/>', x).group(1)
fspver = re.search(r'<option key="#FSPVersion#" value="([^"]+)"/>', x)
print(f"  info configuration.xml FSP version {fspver.group(1) if fspver else '?'} core {core}")
gtm = re.search(r'timer_on_gtm[^>]*>\s*<property id="module.driver.timer.name"[^>]*/>\s*<property id="module.driver.timer.channel" value="enum.mcu.gtm.channels.(\d+)"', x)
gtm = gtm.group(1) if gtm else None
gpts = re.findall(r'<property id="module.driver.timer.name" value="g_gpt(\d+)"/>', x)
vec = rd(f"{P}/{GEN}/vector_data.c")
hal = rd(f"{P}/{GEN}/hal_data.c")
need(bool(vec) and bool(hal), f"{GEN}/ generated")
if gtm:
    need(re.search(rf"GTM{gtm}\b", vec) is not None, f"tick timer GTM{gtm} in vector_data.c (core {core})")
for ch in gpts:
    need(f"g_gpt{ch}_ctrl" in hal, f"g_gpt{ch} instance in hal_data.c")
if "<configSetting" in x:
    need(os.path.exists(f"{P}/{GEN}/pin_data.c"), f"{GEN}/pin_data.c present")
    pins = re.findall(r'altId="(p[0-9a][0-9]).gpt\d+', x)
    pd = rd(f"{P}/{GEN}/pin_data.c")
    for pin in pins:
        port, num = pin[1], pin[2]
        port = {"a": "10", "b": "11"}.get(port, "0" + port)   # PA/PB are ports 10/11 in FSP naming
        need(f"BSP_IO_PORT_{port}_PIN_0{num}" in pd, f"pin {pin.upper()} in pin_data.c")

# pack patches actually landed in the generated tree
asm = rd(one(f"{FSP}/fsp/src/rm_freertos_port/cr*/portASM.asm", "portASM.asm"))
need("POP     {r0-r4, lr}" in asm, "portASM.asm is the FSP 4.3.0 handler (lr bracket, rz-fsp#3 fix)")
need("ulPortInterruptNesting" in asm and "BNE     exit_without_switch" in asm, "portASM.asm has the interrupt-nesting guard (pack patch)")
pc = rd(one(f"{FSP}/fsp/src/rm_freertos_port/cr*/port.c", "port.c"))
need("r8_tick_probe" in pc and "ulPortInterruptNesting" in pc, "port.c has the nesting count + r8_tick_probe hook (pack patch)")
bi = rd(one(f"{FSP}/fsp/src/bsp/mcu/all/cr/bsp_irq.c", "bsp_irq.c"))
need("gic_intid < BSP_ICU_VECTOR_MAX_ENTRIES" in bi, "bsp_irq.c has the vector-table bounds check (pack patch)")
at = rd(one(f"{FSP}/**/libmetal/include/metal/atomic.h", "atomic.h"))
need("METAL_XCORE_FENCE" in at, "libmetal atomic.h has the dmb sy override (pack patch)")
mx = rd(one(f"{FSP}/**/libmetal/include/metal/system/freertos/mutex.h", "mutex.h"))
need("xSemaphoreTake(mutex->m, portMAX_DELAY)" in mx, "libmetal mutex.h blocks on a FreeRTOS semaphore (4.3.0 libmetal; no patch needed)")
rv = rd(one(f"{FSP}/**/open-amp/lib/rpmsg/rpmsg_virtio.c", "rpmsg_virtio.c"))
need("R8_VDEV_STAGE" in rv, "rpmsg_virtio.c has the stage probes (pack patch)")
need("R8_COMPAT_SEND_NOTIFY" in rv, "rpmsg_virtio.c rings the doorbell for every send (pack patch, old-host compatibility)")
vq = rd(one(f"{FSP}/**/open-amp/lib/virtio/virtqueue.c", "virtqueue.c"))
need("R8_COMPAT_ALWAYS_NOTIFY" not in vq, "virtqueue.c is unpatched (no stale edit from an earlier patch_packs.py)")
cfg = f"{P}/{CFG}/aws/FreeRTOSConfig.h"
if os.path.exists(cfg):
    c = rd(cfg)
    need("configTOTAL_HEAP_SIZE" in c and "65536" in c, "FreeRTOSConfig.h heap 65536")
    need("configCHECK_FOR_STACK_OVERFLOW (2)" in c or "configCHECK_FOR_STACK_OVERFLOW (1)" in c, "stack overflow check enabled")
if bad:
    sys.exit(f"check_regen: {len(bad)} problem(s)")
print("check_regen: all good")
