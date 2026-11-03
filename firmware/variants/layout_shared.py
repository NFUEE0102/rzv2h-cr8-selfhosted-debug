#!/usr/bin/env python3
"""Move a core0 project from the per-core carveout layout (base/, EVK column of docs/09) back to
the legacy "shared with CM33" layout the RDK (.176) device tree still uses:
  rsctbl 0x42F00000 "42f00000.rsctbl", vrings 0x43000000/0x43100000 (15 MB window),
  shm 0x43200000/0x43500000, UIO names without the -c0 suffix, black box 0x431F0000.
MPU table is left alone (region 8 = 32 KB and region 9 = 16 MB @0x43000000 cover both layouts).
usage: layout_shared.py <project dir>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import patch, proj_arg  # noqa: E402

P = proj_arg(sys.argv)
patch(f"{P}/script/custom_rzv2h_cr8_0.ld", [
    ("DDR0_CR8_0_START + 0x02F02000 : 0;", "DDR0_CR8_0_START + 0x02F00000 : 0;"),
    ("DDR0_CR8_0_START + 0x03800000 : 0;", "DDR0_CR8_0_START + 0x03000000 : 0;"),
    ("OPENAMP_VRING_LENGTH    = 0x00800000;", "OPENAMP_VRING_LENGTH    = 0x00F00000;"),
], done_marker="0x02F00000 : 0;")
patch(f"{P}/src/rsc_table.h", [
    ('"42f02000.rsctbl-cr8-0"', '"42f00000.rsctbl"'),
    ("(0x42F02000U)", "(0x42F00000U)"),
], done_marker='"42f00000.rsctbl"')
patch(f"{P}/src/OpenAMP_RPMsg_cfg.h", [
    ("(0x43800000U)", "(0x43000000U)"),          # RPMSG_MEM_BASE and CFG_VRING0_BASE0_PA
], allow_multi=True, done_marker='"43000000.vring-ctl0"')
patch(f"{P}/src/OpenAMP_RPMsg_cfg.h", [
    ("(0x43850000U)", "(0x43050000U)"),
    ("(0x43A00000U)", "(0x43200000U)"),
    ('"43800000.vring-ctl0-c0"', '"43000000.vring-ctl0"'),
    ('"43a00000.vring-shm0-c0"', '"43200000.vring-shm0"'),
    ("(0x43900000U)", "(0x43100000U)"),
    ("(0x43950000U)", "(0x43150000U)"),
    ("(0x43D00000U)", "(0x43500000U)"),
    ('"43900000.vring-ctl1-c0"', '"43100000.vring-ctl1"'),
    ('"43d00000.vring-shm1-c0"', '"43500000.vring-shm1"'),
], done_marker='"43100000.vring-ctl1"')
patch(f"{P}/src/r8_blackbox.h", [
    ("(0x439F0000u)", "(0x431F0000u)"),
    ("0x439F0000 = vring-ctl1-c0 UIO 視窗(0x43900000 + 1 MB)的尾端 64 KB。",
     "0x431F0000 = vring-ctl1 UIO 視窗(0x43100000 + 1 MB)的尾端 64 KB(legacy shared layout)。"),
], done_marker="(0x431F0000u)")
print("layout: shared (legacy CM33 column) applied")
