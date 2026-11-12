#!/usr/bin/env python3
"""core0 (per-core layout) project -> CR8 core1 echo + black-box firmware.
Port of the historical make_core1.py (assets/core1-bringup-20260829), minus the git plumbing.
Every item below is load-bearing (docs/10 of the devkit): skip one and the core does not come up.
  A configuration.xml   Core=CR8_1, MHU channel 3->4 (BSP/memory regions/vectors regenerate),
                        tick timer GTM channel 4->5 (a tick channel must never be shared)
  B linker script       custom_rzv2h_cr8_1.ld generated from cr8_0.ld: CR8_0<->CR8_1 token swap
                        in the body + six numeric fixes; SRAM window 0x08200000 (device tree,
                        not the FSP template's 0x081C0000)
  C .cproject           _RZV_CORE and the linker script name
  D platform_info.h     MBX_INT_NUM 314 -> 315 (MHU_MSG4_NS_IRQn)
  E rsc_table.h         rsctbl-cr8-1 / 0x42F04000 (the R8 polls this at run time)
  F OpenAMP_RPMsg_cfg.h whole column +0x800000, UIO names -c0 -> -c1
  G mpu_region_table.c  core1 table region 9: 0x43000000 -> 0x44000000
  H r8_blackbox.h       0x439F0000 -> 0x441F0000
  + blinky: core1 never touches core0's peripherals (LED, GPTs): pure echo + black-box pump
usage: core1_echo.py <project dir>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import patch, proj_arg, rd, wr  # noqa: E402

P = proj_arg(sys.argv)

# ---- A. configuration.xml ----
patch(f"{P}/configuration.xml", [
    ('<option key="Core" value="CR8_0"/>', '<option key="Core" value="CR8_1"/>'),
    ('"enum.mcu.mhu_b.channels.3"', '"enum.mcu.mhu_b.channels.4"'),
    ('<property id="module.driver.rzv.timer.channel" value="enum.mcu.gtm.channels.4"/>',
     '<property id="module.driver.rzv.timer.channel" value="enum.mcu.gtm.channels.5"/>'),
], done_marker='<option key="Core" value="CR8_1"/>')

# ---- B. custom_rzv2h_cr8_1.ld ----
ld1 = f"{P}/script/custom_rzv2h_cr8_1.ld"
if not os.path.exists(ld1):
    src = rd(f"{P}/script/custom_rzv2h_cr8_0.ld")
    marker = "/* Memory Map Definition */"
    head, body = src.split(marker, 1)
    body = (body.replace("CR8_0", "CR8_TMPX").replace("CR8_1", "CR8_0").replace("CR8_TMPX", "CR8_1"))
    for old, new in [
        ("- 0x12040000", "- 0x12080000"),   # ITCM private view (core1 ITCM AXI)
        ("- 0x12020000", "- 0x12060000"),   # DTCM (core1 DTCM AXI 0x120A0000 - 0x00020000)
        ("+ 0x02F02000", "+ 0x02F04000"),   # rsctbl-cr8-1
        ("+ 0x03800000", "+ 0x04000000"),   # vring 0x44000000
    ]:
        if body.count(old) != 1:
            sys.exit(f"FAIL ld body anchor {old!r} x{body.count(old)}")
        body = body.replace(old, new)
    head = head.replace("SRAM_CR8_1_CUSTOM_OFFSET = 0x081C0000;",
                        "SRAM_CR8_1_CUSTOM_OFFSET = 0x08200000;   /* kernel DT 的 cr8-core1 SRAM 窗 = 0x08200000/0x80000(每核 512KB 分法,非 FSP 模板的 0x081C0000)*/")
    head = head.replace("DDR0_CUSTOM_OFFSET = 0x00800000;", "DDR0_CUSTOM_OFFSET = 0x01800000;")
    head = head.replace("FLASH_HEADER_CUSTOM_OFFSET = 0x00200000;", "FLASH_HEADER_CUSTOM_OFFSET = 0x01300000;")
    assert "0x01800000" in head and "0x01300000" in head and "0x08200000" in head, "ld head fixes missed"
    wr(ld1, head + marker + body)
    print("  generated script/custom_rzv2h_cr8_1.ld")

# ---- C. .cproject ----
patch(f"{P}/.cproject", [
    ("_RZV_CORE=CR8_0", "_RZV_CORE=CR8_1"),
    ("custom_rzv2h_cr8_0.ld", "custom_rzv2h_cr8_1.ld"),
], allow_multi=True, done_marker="_RZV_CORE=CR8_1")

# ---- D. platform_info.h ----
pi = rd(f"{P}/src/platform_info.h")
if "MBX_INT_NUM (315)" not in pi:
    m = re.search(r"#define\s+MBX_INT_NUM\s+\(?314\)?[^\n]*", pi)
    if not m:
        sys.exit("FAIL MBX_INT_NUM 314 not found")
    wr(f"{P}/src/platform_info.h", pi.replace(m.group(0), "#define MBX_INT_NUM (315)  /* MHU_MSG4_NS_IRQn — CR8 core1(msg ch4)*/"))
    print("  patched src/platform_info.h (MBX_INT_NUM 315)")

# ---- E. rsc_table.h ----
patch(f"{P}/src/rsc_table.h", [
    ('"42f02000.rsctbl-cr8-0"', '"42f04000.rsctbl-cr8-1"'),
    ("(0x42F02000U)", "(0x42F04000U)"),
], done_marker="rsctbl-cr8-1")

# ---- F. OpenAMP_RPMsg_cfg.h ----
patch(f"{P}/src/OpenAMP_RPMsg_cfg.h", [
    ("(0x43800000U)", "(0x44000000U)"),   # RPMSG_MEM_BASE and CFG_VRING0_BASE0_PA
], allow_multi=True, done_marker="vring-ctl0-c1")
patch(f"{P}/src/OpenAMP_RPMsg_cfg.h", [
    ("(0x43850000U)", "(0x44050000U)"),
    ("(0x43A00000U)", "(0x44200000U)"),
    ('"43800000.vring-ctl0-c0"', '"44000000.vring-ctl0-c1"'),
    ('"43a00000.vring-shm0-c0"', '"44200000.vring-shm0-c1"'),
    ("(0x43900000U)", "(0x44100000U)"),
    ("(0x43950000U)", "(0x44150000U)"),
    ("(0x43D00000U)", "(0x44500000U)"),
    ('"43900000.vring-ctl1-c0"', '"44100000.vring-ctl1-c1"'),
    ('"43d00000.vring-shm1-c0"', '"44500000.vring-shm1-c1"'),
], done_marker="vring-ctl1-c1")

# ---- G. MPU core1 table region 9 ----
mpu = rd(f"{P}/src/mpu_region_table.c")
i = mpu.index("#else")
tail = mpu[i:]
if "0x44000000," not in tail:
    if tail.count("0x43000000,") != 1:
        sys.exit(f"FAIL core1 table region 9 anchor x{tail.count('0x43000000,')}")
    wr(f"{P}/src/mpu_region_table.c", mpu[:i] + tail.replace("0x43000000,", "0x44000000,"))
    print("  patched src/mpu_region_table.c (core1 region 9 -> 0x44000000)")

# ---- H. black box ----
patch(f"{P}/src/r8_blackbox.h", [
    ("(0x439F0000u)", "(0x441F0000u)"),
    ("0x439F0000 = vring-ctl1-c0 UIO 視窗(0x43900000 + 1 MB)的尾端 64 KB。",
     "0x441F0000 = vring-ctl1-c1 UIO 視窗(0x44100000 + 1 MB)的尾端 64 KB(core1)。"),
], done_marker="(0x441F0000u)")

# ---- blinky: no shared peripherals on core1 ----
patch(f"{P}/src/blinky_thread_entry.c", [
    ("""    R8_BB_STAGE(10);
    for (int i = 0; i < 6; i++)
    {
        R_BSP_PinWrite((bsp_io_port_pin_t) BSP_IO_PORT_11_PIN_05,
                       (i & 1) ? BSP_IO_LEVEL_LOW : BSP_IO_LEVEL_HIGH);
        vTaskDelay(configTICK_RATE_HZ / 5);
    }""",
     """    R8_BB_STAGE(10);
    /* core1:LED(P11_05)由 core0 持有,不碰。 */
    vTaskDelay(configTICK_RATE_HZ / 2);"""),
    ("""    R8_BB_STAGE(12);
    pwm_test_entry();      /* 之後就在裡面無限迴圈輪換脈寬 */""",
     """    R8_BB_STAGE(12);
    /* core1:純 echo + 黑盒子。GPT 等共享週邊由 core0 持有,一概不碰
     * (pwm_test_entry 會開 7 顆 GPT —— 那是 core0 的事)。對本核下 PWMC
     * 會因 GPT 未開而回錯誤碼,屬預期行為;JITQ 回全零(探針未 arm)。 */
    {
        extern void r8_blackbox_pump(void);
        for ( ; ; )
        {
            r8_blackbox_pump();
            vTaskDelay(pdMS_TO_TICKS(500));
        }
    }"""),
], done_marker="core1:純 echo")
print("variant: core1-echo applied")
