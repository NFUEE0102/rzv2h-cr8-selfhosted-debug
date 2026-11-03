#!/usr/bin/env python3
"""core0-pwm-plane -> core0-demo: the single-step / fix-the-bug demo firmware (2026-11-03).

Applied on top of core0_pwm_plane.py (same four Pmod CN2 pins, same clamp). Adds
src/demo_servo.c (angle table -> servo pulse on GPT4.B = P75 = CN2 pin 8, with a planted
16-bit overflow bug, built -O0) and calls demo_servo_step() from the pwm_test_entry()
heartbeat loop every 250 ms. Nothing else changes: rpmsg/black box stay as in the plane
build, all other outputs stay silent.

usage: core0_demo.py <project dir>
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import patch, proj_arg  # noqa: E402

P = proj_arg(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__))

dst = f"{P}/src/demo_servo.c"
shutil.copyfile(f"{HERE}/files/demo_servo.c", dst)
print(f"  added {os.path.relpath(dst)}")

patch(f"{P}/src/pwm_test.c", [
    (
        "        extern void r8_blackbox_pump(void);\n"
        "        uint32_t led = 0;\n",
        "        extern void r8_blackbox_pump(void);\n"
        "        extern void demo_servo_step(void);   /* core0-demo: src/demo_servo.c */\n"
        "        uint32_t led = 0;\n",
    ),
    (
        "            r8_blackbox_pump();\n"
        "            led ^= 1u;\n",
        "            r8_blackbox_pump();\n"
        "            demo_servo_step();\n"
        "            led ^= 1u;\n",
    ),
    (
        "            vTaskDelay(pdMS_TO_TICKS(500));\n",
        "            vTaskDelay(pdMS_TO_TICKS(250));   /* core0-demo: 10-step sweep = 2.5 s */\n",
    ),
], done_marker="demo_servo_step")
print("variant: core0-demo applied")
