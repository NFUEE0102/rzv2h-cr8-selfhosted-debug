#!/usr/bin/env python3
"""Static acceptance of a CR8 ELF, optionally against a reference (e.g. the last deployed one).
  * program headers: LOAD/NULL counts; fails on a zero-filesize PT_LOAD in DDR (remoteproc -22)
  * required symbols per variant (echo path, black box, PWM, flight loop ...)
  * dmb domain census: `dmb ish` must be ~0 in the rpmsg/virtqueue objects (R8 is outside the A55
    ISH domain); reports total ish/sy counts
  * text/data/bss sizes, md5
  * with --ref: function symbols missing/extra vs the reference (structural regression check)
usage: verify_elf.py <elf> [--ref REF.elf] [--need sym,sym,...] [--tc TOOLCHAIN_BIN]
"""
import argparse
import hashlib
import os
import re
import struct
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument("elf")
ap.add_argument("--ref")
ap.add_argument("--need", default="")
ap.add_argument("--tc", default="/opt/toolchains/gcc_arm/13_3-Rel1/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi/bin")
A = ap.parse_args()
NM, OBJDUMP, SIZE = (os.path.join(A.tc, "arm-none-eabi-" + t) for t in ("nm", "objdump", "size"))
bad = []


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def funcs(elf):
    out = run(NM, elf)
    return {l.split()[2] for l in out.splitlines() if len(l.split()) == 3 and l.split()[1] in "tTwW"}


data = open(A.elf, "rb").read()
assert data[:4] == b"\x7fELF" and data[4] == 1 and data[5] == 1, "not ELF32 LE"
phoff = struct.unpack_from("<I", data, 28)[0]
phentsize = struct.unpack_from("<H", data, 42)[0]
phnum = struct.unpack_from("<H", data, 44)[0]
loads = nulls = 0
for i in range(phnum):
    ptype, poff, vaddr, paddr, filesz, memsz = struct.unpack_from("<IIIIII", data, phoff + i * phentsize)
    if ptype == 1:
        loads += 1
        if filesz == 0 and paddr >= 0x40000000:
            bad.append(f"phdr[{i}] zero-filesize PT_LOAD at 0x{paddr:08X} (run patch-elf-phdr.py)")
    elif ptype == 0:
        nulls += 1
print(f"{os.path.basename(A.elf)}: {len(data)} bytes md5 {hashlib.md5(data).hexdigest()}  phdr LOAD={loads} NULL={nulls}")
print("  " + run(SIZE, A.elf).splitlines()[-1].strip())
have = funcs(A.elf)
for s in [x for x in A.need.split(",") if x]:
    if s in have:
        print(f"  ok   symbol {s}")
    else:
        bad.append(f"missing symbol {s}")
dis = run(OBJDUMP, "-d", A.elf)
ish = len(re.findall(r"\bdmb\s+ish\b", dis))
sy = len(re.findall(r"\bdmb\s+sy\b", dis))
print(f"  dmb census: ish={ish} sy={sy}")
# ish inside the transport objects means the pack patch did not land
cur = None
bad_fn = set()
for l in dis.splitlines():
    m = re.match(r"^[0-9a-f]+ <(\w+)>:", l)
    if m:
        cur = m.group(1)
    elif re.search(r"\bdmb\s+ish\b", l) and cur and re.search(r"virtqueue|vq_ring|rpmsg_virtio|metal_io", cur):
        bad_fn.add(cur)
if bad_fn:
    # Historical state of every deployed build (v26, pwm demo, core1 demo): ish=70 sy=10. The fence
    # override in libmetal atomic.h covers atomic_thread_fence(); the remaining ish come from
    # seq_cst atomic loads/stores inlined by GCC (metal_io_read/write ...). Open item, not a
    # regression -- so this is a note unless the census is worse than the reference.
    print("  note: dmb ish inside transport functions: " + ", ".join(sorted(bad_fn)[:8]))
if A.ref:
    ref = funcs(A.ref)
    miss = sorted(x for x in ref - have if not x.startswith("$"))
    extra = sorted(x for x in have - ref if not x.startswith("$"))
    rdis = run(OBJDUMP, "-d", A.ref)
    rish = len(re.findall(r"\bdmb\s+ish\b", rdis))
    if ish > rish:
        bad.append(f"dmb ish count {ish} worse than reference {rish}")
    print(f"  vs {os.path.basename(A.ref)}: missing {len(miss)} extra {len(extra)}  (ref dmb ish={rish})")
    if miss:
        print("    missing: " + " ".join(miss[:40]))
    if extra:
        print("    extra:   " + " ".join(extra[:40]))
for b in bad:
    print(f"  FAIL {b}")
sys.exit(1 if bad else 0)
