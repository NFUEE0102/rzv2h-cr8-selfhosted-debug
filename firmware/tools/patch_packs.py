#!/usr/bin/env python3
"""Make an e2studio 2025-01 / RZ/V FSP 3.1.0 installation emit OUR fixed sources every time it
(re)generates project content. The FSP generator copies rzv/ from the .pack archives on every
build, so patching a project's rzv/ tree is futile: the fix has to live in the packs.

Packs (each edit idempotent, marker-checked; the untouched archive is kept as <pack>.orig):

  Renesas.RZV.3.1.0.pack                      (whole-file replacements from fsp-patches/rzv/)
     rzv/fsp/src/rm_freertos_port/cr/portASM.asm   IRQ_Handler saves lr_svc (nested-IRQ data abort)
     rzv/fsp/src/rm_freertos_port/cr/port.c        weak r8_tick_probe() hook in SysTick_Handler
     rzv/fsp/src/bsp/mcu/all/cr/bsp_irq.c          vector-table bounds check
  Linaro.OpenAMP.1.0.0+fsp.3.1.0.pack         (in-place edits)
     rzv/linaro/libmetal/include/metal/atomic.h                  fences -> dmb sy (R8 is outside the A55 ISH domain)
     rzv/linaro/libmetal/include/metal/system/freertos/mutex.h   spin -> spin+block (priority-inversion deadlock) + counter
     rzv/linaro/open-amp/lib/rpmsg/rpmsg_virtio.c                black-box boot-stage probes 0x50..0x55 (weak; no-op without bb)
  Renesas.RZV_board_custom.3.1.0.pack
     .module_descriptions/Renesas##BSP##Board##custom####3.1.0.xml  board@display (2025-01 schema rejects it missing)

usage: patch_packs.py [--e2studio ~/rzv-tools/e2studio] [--fsp-patches <cr8-fw>/fsp-patches] [--check]
Every pack directory is handled: <e2studio>/internal/projectgen/rz_fsp/rzv/packs and the per-user
caches ~/.eclipse/com.renesas.platform_*/internal/projectgen/rz_fsp/rzv/packs (what e2studio reads).
"""
import argparse
import glob
import io
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--e2studio", default="~/rzv-tools/e2studio")
ap.add_argument("--fsp-patches", default=os.path.join(HERE, "..", "fsp-patches"))
ap.add_argument("--check", action="store_true", help="report only, do not write")
A = ap.parse_args()
FSP = os.path.abspath(os.path.expanduser(A.fsp_patches))


def nl_of(s):
    return "\r\n" if "\r\n" in s else "\n"


def sub1(s, old, new, what):
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{what}: anchor found {n}x (need 1): {old[:70]!r}")
    return s.replace(old, new, 1)


# ---------------------------------------------------------------- in-place editors (text -> text)
def edit_atomic_h(s):
    if "METAL_XCORE_FENCE" in s:
        return s
    nl = nl_of(s)
    m = re.search(r"#endif\s+/\*\s*__METAL_ATOMIC__H__\s*\*/", s)
    if not m:
        raise RuntimeError("atomic.h: closing #endif not found")
    block = nl.join([
        "",
        "/* ---------------------------------------------------------------------------",
        " * Cross-core barriers must be System domain (2026-08-24).",
        " * atomic_thread_fence() compiles to `dmb ish` on ARM GCC, but the Cortex-R8 is NOT in",
        " * the Cortex-A55 Inner Shareable domain: an ish barrier gives no cross-core visibility",
        " * on the vrings (symptom: R8 takes the MHU doorbell, reads an avail ring that does not",
        " * yet show the A55 write, answers nothing; both sides wait forever, intermittently).",
        " * Placed after the dispatch above so every branch (<stdatomic.h> / gcc/atomic.h /",
        " * processor/arm/atomic.h) is overridden. */",
        "#define METAL_XCORE_FENCE()    __asm__ __volatile__ (\"dmb sy\" ::: \"memory\")",
        "",
        "#undef  atomic_thread_fence",
        "#define atomic_thread_fence(MO)   METAL_XCORE_FENCE()",
        "#undef  atomic_signal_fence",
        "#define atomic_signal_fence(MO)   METAL_XCORE_FENCE()",
        "", ""])
    return s[:m.start()] + block + s[m.start():]


def edit_mutex_h(s):
    if "METAL_MUTEX_SPINS_BEFORE_BLOCK" in s:
        return s
    nl = nl_of(s)
    old = nl.join([
        "static inline void __metal_mutex_acquire (metal_mutex_t * mutex)",
        "{",
        "    while (atomic_flag_test_and_set(&mutex->v))",
        "    {",
        "        ;",
        "    }",
        "}"])
    new = nl.join([
        "/* Short spin before blocking: most contention ends within microseconds, not worth a",
        " * scheduler round trip; 2000 iterations is a few microseconds on the R8. */",
        "#define METAL_MUTEX_SPINS_BEFORE_BLOCK    (2000U)",
        "",
        "/* Contention counter published by the black box (src/r8_blackbox.c). Weak so a firmware",
        " * without the black box still links; the null check costs nothing. */",
        "extern volatile unsigned int g_metal_mutex_blocks __attribute__((weak));",
        "",
        "static inline void __metal_mutex_acquire (metal_mutex_t * mutex)",
        "{",
        "    unsigned int spins = 0U;",
        "",
        "    while (atomic_flag_test_and_set(&mutex->v))",
        "    {",
        "        if (++spins < METAL_MUTEX_SPINS_BEFORE_BLOCK)",
        "        {",
        "            continue;",
        "        }",
        "        spins = 0U;",
        "",
        "        /* The stock version spins forever. Single core + priority preemption +",
        "         * configUSE_TIME_SLICING = 0: the IpiTask (prio 4) spinning on rdev->lock held",
        "         * by main_task (prio 1) is a guaranteed deadlock -- the holder never runs",
        "         * again. Must be vTaskDelay(), not taskYIELD(): only a real Blocked state lets",
        "         * the lower-priority holder run and release. Renesas' own rzv2h_drone_px4",
        "         * wraps the transport in exactly this kind of lock for the same reason. */",
        "        if (&g_metal_mutex_blocks != 0)",
        "        {",
        "            g_metal_mutex_blocks++;",
        "        }",
        "        if (taskSCHEDULER_RUNNING == xTaskGetSchedulerState())",
        "        {",
        "            vTaskDelay(1);",
        "        }",
        "    }",
        "}"])
    s = sub1(s, old, new, "mutex.h acquire")
    if "task.h" not in s:
        s = sub1(s, " #include <metal/atomic.h>", " #include <metal/atomic.h>" + nl + " #include <FreeRTOS.h>" + nl + " #include <task.h>", "mutex.h includes")
    return s


def edit_rpmsg_virtio_c(s):
    if "R8_VDEV_STAGE" in s:
        return s
    nl = nl_of(s)
    hdr = nl.join([
        "#include <metal/alloc.h>",
        "",
        "/* Black-box boot-stage probes inside rpmsg_init_vdev (2026-08-27): weak, so a firmware",
        " * without src/r8_blackbox.c compiles to a no-op. Stages 0x50..0x55 bracket the two places",
        " * a remote can hang at boot: waiting for the host's DRIVER_OK and creating the virtqueues. */",
        "extern void r8_blackbox_stage_probe(unsigned int n) __attribute__((weak));",
        "#define R8_VDEV_STAGE(n) do { if (r8_blackbox_stage_probe) r8_blackbox_stage_probe(n); } while (0)"])
    s = sub1(s, "#include <metal/alloc.h>", hdr, "rpmsg_virtio.c include")
    s = sub1(s, "    vdev->priv                    = rvdev;",
             "    vdev->priv                    = rvdev;" + nl + "    R8_VDEV_STAGE(0x50);", "rpmsg_virtio.c 0x50")
    s = sub1(s, "        rpmsg_virtio_wait_remote_ready(rvdev);",
             "        R8_VDEV_STAGE(0x52);" + nl + "        rpmsg_virtio_wait_remote_ready(rvdev);" + nl + "        R8_VDEV_STAGE(0x53);",
             "rpmsg_virtio.c wait_remote_ready")
    s = sub1(s, "    status = rpmsg_virtio_create_virtqueues(rvdev, 0, RPMSG_NUM_VRINGS, vq_names, callback);",
             "    R8_VDEV_STAGE(0x54);" + nl + "    status = rpmsg_virtio_create_virtqueues(rvdev, 0, RPMSG_NUM_VRINGS, vq_names, callback);" + nl + "    R8_VDEV_STAGE(0x55);",
             "rpmsg_virtio.c create_virtqueues")
    return s


def edit_board_custom_xml(s):
    old = '<board config="config.board.custom" device="" id="board.custom" version="0" >'
    new = '<board config="config.board.custom" device="" display="Custom User Board (Any Device)" id="board.custom" version="0" >'
    return s.replace(old, new) if old in s else s


def whole_file(name):
    p = os.path.join(FSP, "rzv", name)
    if not os.path.exists(p):
        raise RuntimeError(f"missing {p}")
    data = open(p, "rb").read()
    return lambda cur: data


PLAN = {
    "Renesas.RZV.3.1.0.pack": {
        "rzv/fsp/src/rm_freertos_port/cr/portASM.asm": ("bytes", whole_file("portASM.asm")),
        "rzv/fsp/src/rm_freertos_port/cr/port.c": ("bytes", whole_file("port.c")),
        "rzv/fsp/src/bsp/mcu/all/cr/bsp_irq.c": ("bytes", whole_file("bsp_irq.c")),
    },
    "Linaro.OpenAMP.1.0.0+fsp.3.1.0.pack": {
        "rzv/linaro/libmetal/include/metal/atomic.h": ("text", edit_atomic_h),
        "rzv/linaro/libmetal/include/metal/system/freertos/mutex.h": ("text", edit_mutex_h),
        "rzv/linaro/open-amp/lib/rpmsg/rpmsg_virtio.c": ("text", edit_rpmsg_virtio_c),
    },
    "Renesas.RZV_board_custom.3.1.0.pack": {
        ".module_descriptions/Renesas##BSP##Board##custom####3.1.0.xml": ("text", edit_board_custom_xml),
    },
}


def process_pack(path):
    plan = PLAN[os.path.basename(path)]
    zin = zipfile.ZipFile(path)
    names = set(zin.namelist())
    missing = [n for n in plan if n not in names]
    if missing:
        raise RuntimeError(f"{path}: entries not in archive: {missing}")
    changes = {}
    for name, (kind, fn) in plan.items():
        cur = zin.read(name)
        if kind == "bytes":
            new = fn(cur)
        else:
            txt = cur.decode("utf-8", errors="surrogateescape")
            new = fn(txt).encode("utf-8", errors="surrogateescape")
        if new != cur:
            changes[name] = new
    if not changes:
        print(f"  ok       {path}")
        zin.close()
        return
    print(f"  {'needs' if A.check else 'patch'}    {path}: " + ", ".join(os.path.basename(n) for n in changes))
    if A.check:
        zin.close()
        return
    if not os.path.exists(path + ".orig"):
        shutil.copy2(path, path + ".orig")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = changes.get(item.filename, zin.read(item.filename))
            zout.writestr(item, data)
    zin.close()
    os.replace(tmp, path)


dirs = [os.path.join(os.path.expanduser(A.e2studio), "internal/projectgen/rz_fsp/rzv/packs")]
dirs += glob.glob(os.path.expanduser("~/.eclipse/com.renesas.platform_*/internal/projectgen/rz_fsp/rzv/packs"))
found = 0
for d in dirs:
    if not os.path.isdir(d):
        continue
    print(f"== {d}")
    for pack in PLAN:
        p = os.path.join(d, pack)
        if os.path.exists(p):
            process_pack(p)
            found += 1
        else:
            print(f"  missing  {p}")
# the extracted module-description cache is what the generator parses for the board list
for f in glob.glob(os.path.expanduser("~/.eclipse/com.renesas.platform_*/internal/projectgen/rz_fsp/rzv/modules/Renesas##BSP##Board##custom####3.1.0.xml")):
    s = io.open(f, encoding="utf-8").read()
    t = edit_board_custom_xml(s)
    if t != s:
        print(f"  {'needs' if A.check else 'patch'}    {f}")
        if not A.check:
            io.open(f, "w", encoding="utf-8").write(t)
if not found:
    sys.exit("no packs found - wrong --e2studio path?")
