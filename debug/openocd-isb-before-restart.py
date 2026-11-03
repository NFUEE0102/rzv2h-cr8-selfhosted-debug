#!/usr/bin/env python3
"""Patch OpenOCD src/target/cortex_a.c: execute an ISB (via ITR) right before
restarting the core. Needed when the debug APB is driven through the
system bus (dmem adapter on RZ/V2H CR8): breakpoint register writes only
become visible to the core at its next context synchronisation, so without
this the restart still runs with the previous BVR/BCR contents.

usage: openocd-isb-before-restart.py <openocd-src-dir>
"""
import sys, os

p = os.path.join(sys.argv[1], "src/target/cortex_a.c")
s = open(p).read()
anchor = '''	if ((dscr & DSCR_INSTR_COMP) == 0)
		LOG_TARGET_ERROR(target, "DSCR InstrCompl must be set before leaving debug!");

	retval = mem_ap_write_atomic_u32(armv7a->debug_ap,
			armv7a->debug_base + CPUDBG_DSCR, dscr & ~DSCR_ITR_EN);'''
patch = '''	if ((dscr & DSCR_INSTR_COMP) == 0)
		LOG_TARGET_ERROR(target, "DSCR InstrCompl must be set before leaving debug!");

	/*
	 * Memory-mapped debug APB (e.g. RZ/V2H CR8 via dmem): BVR/BCR writes
	 * made from the system bus only reach the core at its next context
	 * synchronisation. Without this ISB the restart runs with the previous
	 * breakpoint contents (single-step runs away, stale mismatch breakpoint
	 * fires later). Harmless on a real APB-AP path.
	 */
	retval = cortex_a_exec_opcode(target, ARMV4_5_MCR(15, 0, 0, 7, 5, 4), &dscr);
	if (retval != ERROR_OK)
		return retval;

	retval = mem_ap_write_atomic_u32(armv7a->debug_ap,
			armv7a->debug_base + CPUDBG_DSCR, dscr & ~DSCR_ITR_EN);'''
if patch in s:
    print("already patched")
    sys.exit(0)
assert s.count(anchor) == 1, "anchor not found exactly once"
open(p, "w").write(s.replace(anchor, patch))
print("patched", p)
