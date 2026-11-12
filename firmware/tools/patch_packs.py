#!/usr/bin/env python3
"""Make an e2 studio 2026-10 / RZ FSP 4.3.0 installation emit OUR fixed sources every time it
(re)generates project content. The FSP generator copies the FSP tree from the .pack archives on
every build, so patching a project's generated tree is futile: the fix has to live in the packs.

Every edit is an anchored, idempotent, marker-checked text transform applied in place (the
untouched archive is kept as <pack>.orig). Packs are matched by glob, entries by regex, so the
pack version / tree prefix is not hard-coded.

  Renesas.RZV.<ver>.pack
     .../rm_freertos_port/cr8/portASM.asm   interrupt-nesting count + no context switch from a nested
                                            IRQ exit (upstream FreeRTOS ARM_CRx logic; not in 4.3.0)
     .../rm_freertos_port/cr8/port.c        ulPortInterruptNesting definition, weak r8_tick_probe() hook
                                            in SysTick_Handler, weak r8_irq_guard() + nested-yield counter
     .../bsp/mcu/all/cr/bsp_irq.c           vector-table bounds check (+ weak r8_nest_probe / r8_bad_intid)
  Linaro.OpenAMP-freertos.<ver>.pack
     .../libmetal/include/metal/atomic.h                  fences -> dmb sy (R8 is outside the A55 ISH domain)
     (mutex.h: no longer patched -- 4.3.0 libmetal blocks on a FreeRTOS semaphore, which is what the
      3.1.0 spin+block patch emulated)
     .../open-amp/lib/rpmsg/rpmsg_virtio.c                black-box boot-stage probes 0x50..0x55 (weak; no-op without bb)
                                                          + device side rings the doorbell for every message it
                                                          sends (hosts on the older, non role-aware open-amp
                                                          suppress interrupts yet block on them)

usage: patch_packs.py [--e2studio DIR] [--check] [--diff]
       patch_packs.py --test-dir DIR [--check] [--diff]   apply the editors to loose files under DIR (no packs)
Every pack directory is handled: <e2studio>/internal/projectgen/rz_fsp/packs and the per-user
caches ~/.eclipse/com.renesas.platform_*/internal/projectgen/rz_fsp/packs (what e2 studio reads).
"""
import argparse
import difflib
import glob
import os
import re
import shutil
import sys
import zipfile

ap = argparse.ArgumentParser()
ap.add_argument("--e2studio", default="~/rzv-tools/e2studio")
ap.add_argument("--check", action="store_true", help="report only, do not write")
ap.add_argument("--diff", action="store_true", help="print a unified diff of every change")
ap.add_argument("--test-dir", default=None, help="apply the editors to files under this directory instead of packs")
A = ap.parse_args()


def nl_of(s):
    return "\r\n" if "\r\n" in s else "\n"


def sub1(s, old, new, what):
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{what}: anchor found {n}x (need 1): {old[:70]!r}")
    return s.replace(old, new, 1)


def L(nl, *lines):
    return nl.join(lines)


# ---------------------------------------------------------------- FreeRTOS CR8 port (MIT, Amazon)
def edit_portasm(s):
    """4.3.0 IRQ_Handler already saves lr (PUSH/POP {r0-r4, lr}) and aligns the stack; it still has
    no interrupt-nesting count, so a yield requested by a *nested* ISR switches context while the
    outer ISR is still in progress (its SVC-mode state is saved as the task's). Restore the upstream
    ARM_CRx bookkeeping: count on entry, and only consider ulPortYieldRequired at level 0."""
    if "ulPortInterruptNesting" in s:
        return s
    nl = nl_of(s)
    if "POP     {r0-r4, lr}" not in s or "POP     {r2, r3}" not in s:
        raise RuntimeError("portASM.asm: not the FSP 4.3.0 IRQ_Handler (lr bracket / {r2, r3} alignment word missing)")
    s = sub1(s, "    .extern ulCriticalNesting" + nl,
             "    .extern ulCriticalNesting" + nl + "    .extern ulPortInterruptNesting" + nl, "portASM extern")
    s = sub1(s, L(nl, "    /* Push used registers. */", "    PUSH    {r0-r4, r12}", "", ""),
             L(nl, "    /* Push used registers. */", "    PUSH    {r0-r4, r12}", "",
               "    /* Increment the interrupt nesting count (upstream FreeRTOS ARM_CRx logic; the",
               "    FSP port has none).  r2 is dead here -- the MOV below overwrites it -- and r3",
               "    is not live yet. */",
               "    LDR     r3, =ulPortInterruptNesting",
               "    LDR     r2, [r3]",
               "    ADD     r2, r2, #1",
               "    STR     r2, [r3]", "", ""), "portASM nesting increment")
    s = sub1(s, L(nl, "    POP     {r2, r3}", "    ADD     sp, sp, r2", "", ""),
             L(nl, "    POP     {r2, r3}", "    ADD     sp, sp, r2", "",
               "    /* Decrement the interrupt nesting count.  FreeRTOS_EndOfInterrupt has returned,",
               "    so r0-r3 are dead here (both exit paths restore the whole set below). */",
               "    LDR     r1, =ulPortInterruptNesting",
               "    LDR     r0, [r1]",
               "    SUB     r0, r0, #1",
               "    STR     r0, [r1]", "",
               "    /* A context switch is never performed if the nesting count is not 0: doing so",
               "    would save the interrupted context -- an outer ISR still running in SVC mode --",
               "    as if it were a task.  The yield request stays pending and the outermost",
               "    handler honours it on its way out. */",
               "    CMP     r0, #0",
               "    BNE     exit_without_switch", "", ""), "portASM nesting decrement")
    return s


def edit_port_c(s):
    if "ulPortInterruptNesting" in s:
        return s
    nl = nl_of(s)
    s = sub1(s, "volatile uint32_t ulPortYieldRequired = pdFALSE;" + nl,
             L(nl, "volatile uint32_t ulPortYieldRequired = pdFALSE;", "",
               "/* Interrupt nesting depth, maintained by IRQ_Handler in portASM.asm (pack patch): a context",
               " * switch is only taken on the way out of the outermost interrupt, as in upstream FreeRTOS'",
               " * ARM_CRx ports. */",
               "volatile uint32_t ulPortInterruptNesting = 0U;", ""), "port.c nesting definition")
    s = sub1(s, L(nl, "void vApplicationIRQHandler (uint32_t ulICCIAR)", "{",
                  "    bsp_common_interrupt_handler(ulICCIAR);", "}"),
             L(nl, "/* Diagnostics hooks for the black box (src/r8_blackbox.c). All weak: a firmware without",
               " * the black box links and runs unchanged.",
               " *   r8_irq_guard()     ISR-frame corruption detector, called after the user ISR returned",
               " *   g_r8_yield_defer   counts yields requested while still nested (g_current_interrupt_pointer",
               " *                      is already decremented here, so non-zero = still inside an outer ISR).",
               " *                      Observation only: the nesting count in portASM.asm is what defers them. */",
               "extern void r8_irq_guard(uint32_t icciar) __attribute__((weak));",
               "extern volatile uint32_t g_r8_yield_defer __attribute__((weak));",
               "extern uint8_t g_current_interrupt_pointer;", "",
               "void vApplicationIRQHandler (uint32_t ulICCIAR)", "{",
               "    bsp_common_interrupt_handler(ulICCIAR);", "",
               "    if ((0u != g_current_interrupt_pointer) && (pdFALSE != ulPortYieldRequired) && (NULL != &g_r8_yield_defer))",
               "    {",
               "        g_r8_yield_defer++;",
               "    }", "",
               "    if (NULL != r8_irq_guard)",
               "    {",
               "        r8_irq_guard(ulICCIAR);",
               "    }", "}"), "port.c vApplicationIRQHandler")
    s = sub1(s, L(nl, "void SysTick_Handler (__attribute__((unused)) timer_callback_args_t * p_args) /* PRIVILEGED_FUNCTION */", "{",
                  "    uint32_t ulInterruptStatus;", "",
                  "    ulInterruptStatus = portSET_INTERRUPT_MASK_FROM_ISR();"),
             L(nl, "/* Tick probe for the black box (tick liveness / jitter). Lives here rather than in",
               " * vApplicationTickHook because FreeRTOSConfig.h is regenerated on every build. Weak. */",
               "extern void r8_tick_probe(void) __attribute__((weak));", "",
               "void SysTick_Handler (__attribute__((unused)) timer_callback_args_t * p_args) /* PRIVILEGED_FUNCTION */", "{",
               "    uint32_t ulInterruptStatus;", "",
               "    if (NULL != r8_tick_probe) { r8_tick_probe(); }", "",
               "    ulInterruptStatus = portSET_INTERRUPT_MASK_FROM_ISR();"), "port.c SysTick_Handler")
    return s


# ---------------------------------------------------------------- BSP (BSD-3-Clause, Renesas)
def edit_bsp_irq_c(s):
    if "r8_bad_intid" in s:
        return s
    nl = nl_of(s)
    s = sub1(s, "void bsp_common_interrupt_handler (uint32_t id)" + nl,
             L(nl, "/* Black-box probes (src/r8_blackbox.c), weak so a firmware without them links unchanged. */",
               "extern void r8_nest_probe(uint32_t depth) __attribute__((weak));",
               "extern void r8_bad_intid(uint32_t intid) __attribute__((weak));", "",
               "void bsp_common_interrupt_handler (uint32_t id)", ""), "bsp_irq.c externs")
    s = sub1(s, L(nl, "        __enable_irq();", ""),
             L(nl, "        __enable_irq();", "",
               "        /* Nesting-depth probe: g_current_interrupt_num has BSP_PRV_INTERRUPTABLE_NUM entries and",
               "         * the pointer is a uint8_t with no bounds check; the black box records the maximum. */",
               "        if (NULL != r8_nest_probe)",
               "        {",
               "            r8_nest_probe((uint32_t) g_current_interrupt_pointer);",
               "        }", ""), "bsp_irq.c nest probe")
    s = sub1(s, L(nl, "        /* Branch to an interrupt handler. */", "        g_vector_table[gic_intid]();"),
             L(nl, "        /* Bounds check before dispatch: gic_intid is only masked to 0..1023 (BSP_PRV_ID_MASK) but",
               "         * the table has BSP_ICU_VECTOR_MAX_ENTRIES entries. Seen on the RZ/V2H CR8: ICCIAR = 876",
               "         * read g_vector_table[876] out of a neighbouring object and called it. Out of range is not",
               "         * dispatched (the caller still writes ICCEOIR, so the GIC side completes normally). */",
               "        if (gic_intid < BSP_ICU_VECTOR_MAX_ENTRIES)",
               "        {",
               "            /* Branch to an interrupt handler. */",
               "            g_vector_table[gic_intid]();",
               "        }",
               "        else if (NULL != r8_bad_intid)",
               "        {",
               "            r8_bad_intid((uint32_t) gic_intid);",
               "        }",
               "        else",
               "        {",
               "            /* no probe: skip silently */",
               "        }"), "bsp_irq.c bounds check")
    return s


# ---------------------------------------------------------------- libmetal / OpenAMP (BSD-3-Clause)
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


def edit_rpmsg_virtio_c(s):
    """Boot-stage probes in rpmsg_init_vdev_with_config() (open-amp 2023.x as shipped in FSP 4.3.0)."""
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
    s = sub1(s, "	vdev->priv = rvdev;", "	vdev->priv = rvdev;" + nl + "	R8_VDEV_STAGE(0x50);", "rpmsg_virtio.c 0x50")
    s = sub1(s, "		status = rpmsg_virtio_wait_remote_ready(rvdev);",
             "		R8_VDEV_STAGE(0x52);" + nl + "		status = rpmsg_virtio_wait_remote_ready(rvdev);" + nl + "		R8_VDEV_STAGE(0x53);",
             "rpmsg_virtio.c wait_remote_ready")
    s = sub1(s, "	status = virtio_create_virtqueues(vdev, 0, RPMSG_NUM_VRINGS,",
             "	R8_VDEV_STAGE(0x54);" + nl + "	status = virtio_create_virtqueues(vdev, 0, RPMSG_NUM_VRINGS,",
             "rpmsg_virtio.c create_virtqueues")
    s = sub1(s, "					  vq_names, callback, NULL);",
             "					  vq_names, callback, NULL);" + nl + "	R8_VDEV_STAGE(0x55);",
             "rpmsg_virtio.c after create_virtqueues")
    # Device side: ring the doorbell for every message we send, as the 3.x code did. The open-amp in
    # FSP 4.3.0 is role-aware and skips the notification when the host set VRING_AVAIL_F_NO_INTERRUPT;
    # the user-space hosts on the A55 (Renesas rpmsg samples, anything on the same older libopen_amp)
    # are not role-aware: their virtqueue_disable_cb() sets that flag on every queue, yet they block on
    # the MHU interrupt. Without this the name-service announcement sits unseen until the host's 15 s
    # poll timeout. Only the send path is forced; buffer returns still honour the flag (the 3.x device
    # never notified for those), so the doorbell count per message is what it was.
    s = sub1(s, L(nl, "\t/* Let the other side know that there is a job to process. */",
                  "\tvirtqueue_kick(rvdev->svq);"),
             L(nl, "\t/* Let the other side know that there is a job to process. */",
               "\tvirtqueue_kick(rvdev->svq);",
               "\t/* R8_COMPAT_SEND_NOTIFY (pack patch): hosts on the older, non role-aware open-amp set",
               "\t * VRING_AVAIL_F_NO_INTERRUPT on every queue but still block on the doorbell. */",
               "\tif (VIRTIO_ROLE_IS_DEVICE(rvdev->vdev) && rvdev->svq->notify &&",
               "\t    (rvdev->svq->vq_ring.avail->flags & VRING_AVAIL_F_NO_INTERRUPT))",
               "\t\trvdev->svq->notify(rvdev->svq);"),
             "rpmsg_virtio.c send notify")
    return s


# pack glob -> [(entry regex, editor)]; each regex must match exactly one entry of the archive
PLAN = {
    "Renesas.RZV.4.*.pack": [
        (r".*/rm_freertos_port/cr8?/portASM\.asm$", edit_portasm),
        (r".*/rm_freertos_port/cr8?/port\.c$", edit_port_c),
        (r".*/bsp/mcu/all/cr/bsp_irq\.c$", edit_bsp_irq_c),
    ],
    "Linaro.OpenAMP-freertos.4.*.pack": [
        (r".*/libmetal/include/metal/atomic\.h$", edit_atomic_h),
        (r".*/open-amp/lib/rpmsg/rpmsg_virtio\.c$", edit_rpmsg_virtio_c),
    ],
}
ALL_EDITORS = [e for v in PLAN.values() for e in v]


def apply_text(name, cur, fn):
    txt = cur.decode("utf-8", errors="surrogateescape")
    new = fn(txt)
    if A.diff and new != txt:
        sys.stdout.writelines(difflib.unified_diff(txt.splitlines(True), new.splitlines(True), name + " (orig)", name + " (patched)"))
    return new.encode("utf-8", errors="surrogateescape")


def resolve(names, plan, where):
    out = []
    for rx, fn in plan:
        hits = [n for n in names if re.match(rx, n)]
        if len(hits) != 1:
            raise RuntimeError(f"{where}: entry regex {rx!r} matched {len(hits)} entries: {hits[:5]}")
        out.append((hits[0], fn))
    return out


def process_pack(path, plan):
    """Every run starts from the pristine archive (<pack>.orig once it exists), so an editor that
    changed between versions of this script replaces its old output instead of stacking on it."""
    zin = zipfile.ZipFile(path)
    pristine = zipfile.ZipFile(path + ".orig") if os.path.exists(path + ".orig") else zin
    entries = dict(resolve(zin.namelist(), plan, path))
    changes = {}
    for name in zin.namelist():
        if name.endswith("/"):
            continue
        cur = zin.read(name)
        if name in entries:
            new = apply_text(name, pristine.read(name), entries[name])
        elif pristine is not zin:
            new = pristine.read(name)          # an entry an older patch_packs.py edited: back to pristine
        else:
            new = cur
        if new != cur:
            changes[name] = new
    if pristine is not zin:
        pristine.close()
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


def main_test_dir(root):
    """Loose-file mode: every editor whose regex matches a file under root is applied to it."""
    files = []
    for d, _, fs in os.walk(root):
        for f in fs:
            files.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/"))
    n = 0
    for rx, fn in ALL_EDITORS:
        for f in [x for x in files if re.match(rx, x)]:
            p = os.path.join(root, f)
            cur = open(p, "rb").read()
            new = apply_text(f, cur, fn)
            print(f"  {'changed' if new != cur else 'ok     '}  {f}")
            if new != cur and not A.check:
                open(p, "wb").write(new)
            n += 1
    if not n:
        sys.exit("test-dir: no file matched any editor")


if A.test_dir:
    main_test_dir(os.path.abspath(os.path.expanduser(A.test_dir)))
    sys.exit(0)

E2S = os.path.expanduser(A.e2studio)
# 4.3.0: <e2studio>/internal/projectgen/rz_fsp/packs ; 3.1.0 had rz_fsp/rzv/packs
dirs = sorted(glob.glob(os.path.join(E2S, "internal/projectgen/rz_fsp/packs")) + glob.glob(os.path.join(E2S, "internal/projectgen/rz_fsp/*/packs")))
dirs += sorted(glob.glob(os.path.expanduser("~/.eclipse/com.renesas.platform_*/internal/projectgen/rz_fsp/packs")) + glob.glob(os.path.expanduser("~/.eclipse/com.renesas.platform_*/internal/projectgen/rz_fsp/*/packs")))
found = 0
for d in dirs:
    if not os.path.isdir(d):
        continue
    if not glob.glob(os.path.join(d, "Renesas.RZV.4.*.pack")):
        continue                       # another install's cache (e.g. RZ/V FSP 3.x): not ours to touch
    print(f"== {d}")
    for pat, plan in PLAN.items():
        hits = sorted(glob.glob(os.path.join(d, pat)))
        hits = [h for h in hits if not h.endswith((".orig", ".tmp"))]
        if not hits:
            print(f"  missing  {os.path.join(d, pat)}")
            continue
        for p in hits:
            process_pack(p, plan)
            found += 1
if not found:
    sys.exit("no packs found - wrong --e2studio path?")
