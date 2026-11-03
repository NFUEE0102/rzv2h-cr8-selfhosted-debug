#!/usr/bin/env python3
"""Prove the FSP generator really regenerated a project from its configuration.xml.
e2studio caches by timestamp and can silently skip regeneration (a GTM-channel change once never
reached rzv_gen/ and two cores ran on one tick timer). Checks after a build:
  * rzv_gen/vector_data.c names the GTM tick channel configured in the XML
  * rzv_gen/hal_data.c defines every g_gpt<N> module the XML declares
  * rzv_gen/pin_data.c is present when the XML has pin settings
  * the generated FSP port carries our pack patches (lr save, tick hook, barrier override)
usage: check_regen.py <project dir>
"""
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


core = re.search(r'<option key="Core" value="(\w+)"/>', x).group(1)
gtm = re.search(r'timer_on_gtm[^>]*>\s*<property id="module.driver.timer.name"[^>]*/>\s*<property id="module.driver.timer.channel" value="enum.mcu.gtm.channels.(\d+)"', x)
gtm = gtm.group(1) if gtm else None
gpts = re.findall(r'<property id="module.driver.timer.name" value="g_gpt(\d+)"/>', x)
vec = io.open(f"{P}/rzv_gen/vector_data.c", encoding="utf-8", errors="replace").read() if os.path.exists(f"{P}/rzv_gen/vector_data.c") else ""
hal = io.open(f"{P}/rzv_gen/hal_data.c", encoding="utf-8", errors="replace").read() if os.path.exists(f"{P}/rzv_gen/hal_data.c") else ""
need(bool(vec) and bool(hal), "rzv_gen/ generated")
if gtm:
    need(re.search(rf"GTM{gtm}\b", vec) is not None, f"tick timer GTM{gtm} in vector_data.c (core {core})")
for ch in gpts:
    need(f"g_gpt{ch}_ctrl" in hal, f"g_gpt{ch} instance in hal_data.c")
if "<configSetting" in x:
    need(os.path.exists(f"{P}/rzv_gen/pin_data.c"), "rzv_gen/pin_data.c present")
    pins = re.findall(r'altId="(p[0-9a][0-9]).gpt\d+', x)
    pd = io.open(f"{P}/rzv_gen/pin_data.c", encoding="utf-8", errors="replace").read() if os.path.exists(f"{P}/rzv_gen/pin_data.c") else ""
    for pin in pins:
        port, num = pin[1], pin[2]
        port = {"a": "10", "b": "11"}.get(port, "0" + port)   # PA/PB are ports 10/11 in FSP naming
        need(f"BSP_IO_PORT_{port}_PIN_0{num}" in pd, f"pin {pin.upper()} in pin_data.c")
bsp = io.open(f"{P}/rzv_gen/bsp_clock_cfg.h", encoding="utf-8", errors="replace").read() if os.path.exists(f"{P}/rzv_gen/bsp_clock_cfg.h") else ""
# pack patches actually landed in the generated tree
asm = f"{P}/rzv/fsp/src/rm_freertos_port/cr/portASM.asm"
need(os.path.exists(asm) and "PUSH    {r0-r4, r12, lr}" in io.open(asm, encoding="utf-8", errors="replace").read(), "portASM.asm has the lr_svc save (pack patch)")
pc = f"{P}/rzv/fsp/src/rm_freertos_port/cr/port.c"
need(os.path.exists(pc) and "r8_tick_probe" in io.open(pc, encoding="utf-8", errors="replace").read(), "port.c has the r8_tick_probe hook (pack patch)")
at = f"{P}/rzv/linaro/libmetal/include/metal/atomic.h"
need(os.path.exists(at) and "METAL_XCORE_FENCE" in io.open(at, encoding="utf-8", errors="replace").read(), "libmetal atomic.h has the dmb sy override (pack patch)")
mx = f"{P}/rzv/linaro/libmetal/include/metal/system/freertos/mutex.h"
need(os.path.exists(mx) and "METAL_MUTEX_SPINS_BEFORE_BLOCK" in io.open(mx, encoding="utf-8", errors="replace").read(), "libmetal mutex.h has spin+block (pack patch)")
rv = f"{P}/rzv/linaro/open-amp/lib/rpmsg/rpmsg_virtio.c"
need(os.path.exists(rv) and "R8_VDEV_STAGE" in io.open(rv, encoding="utf-8", errors="replace").read(), "rpmsg_virtio.c has the stage probes (pack patch)")
cfg = f"{P}/rzv_cfg/aws/FreeRTOSConfig.h"
if os.path.exists(cfg):
    c = io.open(cfg, encoding="utf-8", errors="replace").read()
    need("configTOTAL_HEAP_SIZE" in c and "65536" in c, "FreeRTOSConfig.h heap 65536")
    need("configCHECK_FOR_STACK_OVERFLOW (2)" in c or "configCHECK_FOR_STACK_OVERFLOW (1)" in c, "stack overflow check enabled")
if bad:
    sys.exit(f"check_regen: {len(bad)} problem(s)")
print("check_regen: all good")
