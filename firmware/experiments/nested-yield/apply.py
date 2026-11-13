#!/usr/bin/env python3
"""core1-echo -> exp-nested-yield: firmware for the nested-interrupt context-switch experiment.

Applied on top of core1_echo.py. Two edits to the application, nothing in the FSP:
  src/rzv2_rproc.c        the MHU doorbell callback ends with portYIELD_FROM_ISR(), the documented
                          FreeRTOS idiom after xSemaphoreGiveFromISR() (the sample omits it and
                          leaves xHigherPriorityTaskWoken uninitialised)
  src/platform_info.c     the notification task calls exp_nested_yield_probe() after each wake-up
  src/exp_nested_yield.c  the probe (see its header comment)

usage: apply.py <project dir> [--workload 0|1|2]   (default 1; see exp_nested_yield.c)
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "variants"))
from common import patch, proj_arg  # noqa: E402

P = proj_arg(sys.argv)

dst = f"{P}/src/exp_nested_yield.c"
shutil.copyfile(f"{HERE}/exp_nested_yield.c", dst)
print(f"  added {os.path.relpath(dst)}")
WORKLOAD = sys.argv[sys.argv.index("--workload") + 1] if "--workload" in sys.argv else "1"
if WORKLOAD not in ("0", "1", "2"):
    sys.exit("--workload must be 0, 1 or 2")
with open(f"{P}/src/exp_config.h", "w", newline=chr(10)) as f:
    f.write(f"#define EXP_WORKLOAD ({WORKLOAD})" + chr(10))
print(f"  workload {WORKLOAD}")

patch(f"{P}/src/rzv2_rproc.c", [
    ("    signed portBASE_TYPE xHigherPriorityTaskWoken;\n",
     "    signed portBASE_TYPE xHigherPriorityTaskWoken = pdFALSE;\n"),
    ("        xSemaphoreGiveFromISR(ipi.ipi_sem_id[val], &xHigherPriorityTaskWoken);\n",
     "        xSemaphoreGiveFromISR(ipi.ipi_sem_id[val], &xHigherPriorityTaskWoken);\n"
     "        portYIELD_FROM_ISR(xHigherPriorityTaskWoken);   /* exp-nested-yield */\n"),
], done_marker="exp-nested-yield")

patch(f"{P}/src/r8_blackbox.c", [
    ("void r8_irq_guard (uint32_t icciar)\n{\n",
     "extern void exp_irq_exit_hook(uint32_t icciar);   /* exp-nested-yield */\n"
     "void r8_irq_guard (uint32_t icciar)\n{\n"
     "    exp_irq_exit_hook(icciar);\n"),
], done_marker="exp-nested-yield")

patch(f"{P}/src/platform_info.c", [
    ("static void IpiTaskId(void * exinf);\n",
     "static void IpiTaskId(void * exinf);\n"
     "extern void exp_nested_yield_probe(void);   /* exp-nested-yield: src/exp_nested_yield.c */\n"),
    ("        g_ipcts_task = IPCTS_GTCNT;   /* T2 */\n",
     "        g_ipcts_task = IPCTS_GTCNT;   /* T2 */\n"
     "        exp_nested_yield_probe();\n"),
], done_marker="exp-nested-yield")
