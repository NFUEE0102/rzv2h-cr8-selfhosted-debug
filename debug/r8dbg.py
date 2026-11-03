#!/usr/bin/env python3
"""Halt / inspect / single-step a Cortex-R8 core from A55 Linux via its
memory-mapped ARMv7 debug registers (no JTAG probe needed).

Needs: board booted with MD_BOOT3=1 (EVK: DSW1-7 ON) and the CR8 cluster
started by remoteproc (that sets CPG_LP_CR8_CTL3; without it any access to
0x1F8xxxxx wedges the bus and the whole board hangs).

Usage: sudo r8dbg.py [--core 0|1] status|halt|regs|step [N]|resume|pcs [N]
"""
import ctypes, mmap, os, sys, time

CPG_BASE, CTL3 = 0x10420000, 0xC44
DBG_BASE = {0: 0x1F810000, 1: 0x1F812000}

# ARMv7 debug register offsets
DTRRX, ITR, PCSR, DSCR, DTRTX, DRCR = 0x080, 0x084, 0x084, 0x088, 0x08C, 0x090
BVR0, BCR0 = 0x100, 0x140
OSLSR, PRSR, LAR, LSR = 0x304, 0x314, 0xFB0, 0xFB4

HALTED, RESTARTED = 1 << 0, 1 << 1
INTDIS, ITREN, HDBGEN = 1 << 11, 1 << 13, 1 << 14
INSTRCOMPL, TXFULL = 1 << 24, 1 << 29
MOE = {0: "halt request", 1: "breakpoint", 2: "async watchpoint", 3: "BKPT",
       4: "external halt", 5: "vector catch", 10: "sync watchpoint"}


class Mem:
    def __init__(self, base):
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self.mm = mmap.mmap(self.fd, 0x1000, offset=base)

    def r(self, off):  # one 32-bit load (APB needs word access)
        return ctypes.c_uint32.from_buffer(self.mm, off).value

    def w(self, off, val):
        ctypes.c_uint32.from_buffer(self.mm, off).value = val & 0xFFFFFFFF


def wait(cond, what, timeout=0.5, fatal=True):
    t = time.time() + timeout
    while not cond():
        if time.time() > t:
            if fatal:
                sys.exit(f"timeout waiting for {what}")
            return False
    return True


class R8:
    def __init__(self, core):
        cpg = Mem(CPG_BASE)
        ctl3 = cpg.r(CTL3)
        if not ctl3 & (1 << 12):
            sys.exit(f"CPG_LP_CR8_CTL3=0x{ctl3:08X}: debug APB not ready "
                     "(start the CR8 with remoteproc first). Refusing to touch it.")
        self.d = Mem(DBG_BASE[core])
        self.d.w(LAR, 0xC5ACCE55)          # unlock memory-mapped writes

    dscr = property(lambda s: s.d.r(DSCR))

    def set_dscr(self, setb=0, clr=0):
        self.d.w(DSCR, (self.dscr | setb) & ~clr)

    # --- run control -------------------------------------------------------
    def halt(self):
        if not self.dscr & HALTED:
            self.d.w(0x090, 1)                       # DRCR.HaltReq
            wait(lambda: self.dscr & HALTED, "halt")
        self.set_dscr(ITREN)
        self.r0 = self.reg(0)                        # r0 is our scratch

    def park(self):
        """Leave the core halted with its real r0 (the next run reads it back)."""
        self.write_reg0(self.r0)

    def restart(self):
        self.d.w(BCR0, 0)
        # Make the BCR0 disable effective before running: a stale armed
        # mismatch breakpoint with halting debug off becomes a Prefetch Abort.
        self.exe(0xF57FF06F)                         # ISB
        self.write_reg0(self.r0)                     # put r0 back
        self.set_dscr(clr=ITREN)
        self.d.w(DRCR, 0x6)                          # restart + clear sticky
        wait(lambda: self.dscr & RESTARTED, "restart")

    # --- instruction transfer ---------------------------------------------
    def exe(self, insn):
        self.d.w(ITR, insn)
        wait(lambda: self.dscr & INSTRCOMPL, f"ITR 0x{insn:08X}")

    def reg(self, n):  # MCR p14,0,Rn,c0,c5,0 -> DTRTX
        self.exe(0xEE000E15 | (n << 12))
        wait(lambda: self.dscr & TXFULL, "DTRTX")
        return self.d.r(DTRTX)

    def write_reg0(self, val):  # DTRRX -> MRC p14,0,r0,c0,c5,0
        self.d.w(DTRRX, val)
        self.exe(0xEE100E15)

    def cpsr(self):
        self.exe(0xE10F0000)                         # MRS r0, CPSR
        return self.reg(0)

    def pc(self, cpsr):
        self.exe(0xE1A0000F)                         # MOV r0, pc
        return self.reg(0) - (4 if cpsr & 0x20 else 8)

    def regs(self):
        out = {f"r{n}": self.reg(n) for n in range(1, 15)}
        out["r0"] = self.r0
        c = self.cpsr()
        out["cpsr"], out["pc"] = c, self.pc(c)
        return out

    def step(self):
        c = self.cpsr()
        pc = self.pc(c)
        bas = 0xF if not c & 0x20 else (0xC if pc & 2 else 0x3)
        # BRP0: unlinked instruction-address MISMATCH, any mode
        self.d.w(BVR0, pc & ~3)
        self.d.w(BCR0, (4 << 20) | (bas << 5) | (3 << 1) | 1)
        # External writes to BVR/BCR only take effect at the core's next
        # context synchronisation; without this ISB the restart still uses
        # the previous step's BVR and every other step stops in place.
        self.exe(0xF57FF06F)                         # ISB
        self.write_reg0(self.r0)
        self.set_dscr(HDBGEN | INTDIS, ITREN)        # no IRQ inside the step
        self.d.w(DRCR, 0x6)
        # HALTED still reads 1 until the restart takes effect: wait for
        # RESTARTED first, otherwise every other step is a no-op.
        ok = (wait(lambda: self.dscr & RESTARTED, "step restart", fatal=False)
              and wait(lambda: self.dscr & HALTED, "step halt", fatal=False))
        self.d.w(BCR0, 0)  # takes effect at the ISB in restart()/next step
        if not ok:  # breakpoint never hit: don't leave IRQs masked while running
            self.d.w(DRCR, 1)
            wait(lambda: self.dscr & HALTED, "fallback halt")
            self.set_dscr(ITREN, HDBGEN | INTDIS)
            self.r0 = self.reg(0)
            self.park()
            sys.exit("step: mismatch breakpoint did not fire; core re-halted")
        self.set_dscr(ITREN, HDBGEN | INTDIS)
        self.r0 = self.reg(0)
        c = self.cpsr()
        return pc, self.pc(c), c


def show(r8, regs):
    d = r8.dscr
    print(f"DSCR=0x{d:08X} halted={d & 1} reason={MOE.get((d >> 2) & 0xF, (d >> 2) & 0xF)}")
    mode = {0x10: "USR", 0x11: "FIQ", 0x12: "IRQ", 0x13: "SVC", 0x17: "ABT",
            0x1B: "UND", 0x1F: "SYS"}.get(regs["cpsr"] & 0x1F, "?")
    print(f"pc=0x{regs['pc']:08X} cpsr=0x{regs['cpsr']:08X} ({mode}, "
          f"{'Thumb' if regs['cpsr'] & 0x20 else 'ARM'}, I={regs['cpsr'] >> 7 & 1})")
    for n in range(0, 15, 4):
        print("  " + "  ".join(f"{'r%d' % k:>3}=0x{regs['r%d' % k]:08X}"
                               for k in range(n, min(n + 4, 15))))


def main():
    a = sys.argv[1:]
    core = 0
    if a[:1] == ["--core"]:
        core, a = int(a[1]), a[2:]
    cmd = a[0] if a else "status"
    r8 = R8(core)
    if cmd == "status":
        print(f"DSCR=0x{r8.dscr:08X} OSLSR=0x{r8.d.r(OSLSR):08X} "
              f"PRSR=0x{r8.d.r(PRSR):08X} LSR=0x{r8.d.r(LSR):08X}")
    elif cmd == "pcs":
        for _ in range(int(a[1]) if len(a) > 1 else 10):
            print(f"0x{r8.d.r(PCSR):08X}")
    elif cmd in ("halt", "regs"):
        r8.halt()
        show(r8, r8.regs())
        r8.park()
    elif cmd == "step":
        r8.halt()
        for _ in range(int(a[1]) if len(a) > 1 else 1):
            old, new, c = r8.step()
            print(f"step 0x{old:08X} -> 0x{new:08X} ({'T' if c & 0x20 else 'A'})")
        show(r8, r8.regs())
        r8.park()
    elif cmd == "resume":
        if r8.dscr & HALTED:
            r8.set_dscr(ITREN)
            r8.r0 = r8.reg(0)
            r8.restart()
        print(f"DSCR=0x{r8.dscr:08X} running={not r8.dscr & HALTED}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
