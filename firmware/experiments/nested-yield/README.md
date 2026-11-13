# Experiment: a context switch requested by a nested interrupt (RZ FSP 4.3.0, Cortex-R8)

The FreeRTOS port of RZ FSP 4.3.0 (`rm_freertos_port/cr8/portASM.asm`) enables nested
interrupts but has no interrupt-nesting count: `IRQ_Handler` switches tasks whenever
`ulPortYieldRequired` is set, also on the way out of a *nested* interrupt. This experiment
checks on the RZ/V2H EVK what that does, and that the nesting count our
[`patch_packs.py`](../../tools/patch_packs.py) adds prevents it.

Result, 2026-11-13, core1 of the EVK:

| Image | Echoes | Nested yields | Task ran inside an unfinished ISR | Outcome |
|---|---|---|---|---|
| vendor handler, run 1 | 35,029 | 81 | 63 wake-ups | Undefined Instruction after about 5 s |
| vendor handler, run 2 | 5,962 | 15 | 12 wake-ups | Data Abort after about 1 s |
| vendor handler, run 3 | 4,853 | 15 | 10 wake-ups | Data Abort after about 1 s |
| with the nesting count | 850,101 | 979 | 0 | no fault in 310 s |

"Vendor handler" is the `portASM.asm` of the v4.3.0 pack, byte for byte. Both images are built
from the same sources; only that one file differs.

## What the firmware does

`exp-nested-yield` is the `core1-echo` variant with two application edits ([apply.py](apply.py)):

1. The MHU doorbell callback ends with `portYIELD_FROM_ISR(xHigherPriorityTaskWoken)`, the
   documented FreeRTOS idiom after `xSemaphoreGiveFromISR()`. The sample omits the call (and
   leaves the variable uninitialised), so the notification task is only picked up later.
2. A background task at `tskIDLE_PRIORITY` that just computes. Without it nothing shows: see
   "Why the stock demo does not hit this".

The doorbell interrupt has priority 12 and the 1 kHz tick priority 14, so under an rpmsg echo
flood the doorbell nests into the tick ISR a few times per second. Two probes
([exp_nested_yield.c](exp_nested_yield.c)) record what happens and mirror the counters into the
black-box window, where [run-on-evk.sh](run-on-evk.sh) reads them from Linux.

## What was observed with the vendor handler

- The notification task was switched in while the tick ISR was still in progress: the BSP count
  of interrupts in progress (`g_current_interrupt_pointer`) read 1 from task context, and the
  GIC running priority read `0xE0` (the tick) instead of `0xFF` (idle).
- The tick was held off for as long as that state lasted. While the tick timer itself completed
  three periods, the FreeRTOS tick count advanced by 0 (8 of 8 samples); in the normal state it
  advanced by 3 (8 of 8 samples).
- All three runs ended in a CPU exception within seconds. The fault addresses fit one mechanism.
  The interrupted ISR runs in SVC mode, and `lr_svc` is not part of a task context. Any SVC taken
  while that ISR is suspended (every `portYIELD()` is one) overwrites `lr_svc` with its own return
  address. When the suspended ISR is resumed and returns from a leaf function with `bx lr`, it
  lands on the instruction after that `svc 0`, in ARM state inside Thumb code:
  - run 1: Undefined Instruction at `prvIdleTask+0xA`, the second instruction after the
    `svc 0` of the idle task's `taskYIELD()`;
  - runs 2 and 3: Data Abort with the fault two words after the `svc 0` in `xQueueSemaphoreTake()`.

  This was read from the fault records and the disassembly, not single-stepped.

With the nesting count, all 979 nested yield requests were left pending and taken by the outer
interrupt on its way out; no task ever ran inside an ISR.

## Why the stock demo does not hit this

Two things hide it, and neither is a guard:

- The sample's MHU callback never requests a switch from the ISR.
- The idle hook of the port keeps the scheduler suspended around its `WFI`
  (`vTaskSuspendAll()` / `xTaskResumeAll()`). When the interrupted task is the idle task, the
  nested exit still runs `portSAVE_CONTEXT` / `vTaskSwitchContext()` / `portRESTORE_CONTEXT`, but
  the kernel declines to switch. [results/vendor-idle-only.txt](results/vendor-idle-only.txt) is
  that case: 251 nested yields, none of them switched.

So the conditions are: two interrupt priorities in use, an ISR that calls
`portYIELD_FROM_ISR(pdTRUE)`, and any task other than idle being interrupted.

## An ordinary application (`exp-normal-app`)

The flood above is a stress test. The second variant asks whether an application written the
usual way is affected. Same two probes, same MHU callback, but the workload is a 100 Hz control
task (about 1 ms of work per period, `vTaskDelayUntil`) and a housekeeping task (about 3 ms of
work, then 7 ms asleep), so the CPU is idle more than half of the time. Linux sends 200 messages
per second (the echo client with a 5 ms pause between sends).

| Image | Echoes | Nested yields | Task ran inside an unfinished ISR | Outcome |
|---|---|---|---|---|
| vendor handler, run 1 | 2,648 | 8 | 7 wake-ups | Data Abort after about 20 s |
| vendor handler, run 2 | 3,947 | 4 | 3 wake-ups | Data Abort after about 26 s |
| vendor handler, run 3 | 4,806 | 8 | 7 wake-ups | no fault yet when the run was cut short at 31 s |
| with the nesting count | 110,531 | 154 | 0 | no fault in 915 s |

Both faults are again two words after the `svc 0` in `xQueueSemaphoreTake()`. Run 3 was ended by
a mistake in the run script (its success test did not match the shorter runs; fixed since).

The control run ([results/normal-guard-run1.txt](results/normal-guard-run1.txt)) left all 154
nested yield requests to the outer interrupt.

One thing is unexplained. A first attempt at the control run ended after about 80 s because the
whole EVK reset, Linux included, with nothing in the kernel log; the black boxes did not survive.
It came right after the three vendor-handler runs, which had deliberately crashed or corrupted
core1, so collateral damage from those is a candidate, but that is a guess. After the reboot the
control ran its 15 minutes without incident. The logs of the three vendor-handler runs were on
the tmpfs of the board and went with the reset; their rows above are the status lines printed
during the runs.

## Reproducing

Linux host with e² studio 2026-10 + RZ FSP 4.3.0 (see [docs/build-firmware.md](../../../docs/build-firmware.md)):

```bash
bash experiments/nested-yield/build.sh      # out/exp-nested-yield-guard.elf and -vendor.elf
```

```bash
bash experiments/nested-yield/build.sh exp-normal-app
```

Copy both images to `/lib/firmware` on the board and `run-on-evk.sh` next to the board tools, then
as root on the board:

```bash
bash run-on-evk.sh <vendor image name> 120
```

```bash
bash run-on-evk.sh <guard image name> 300
```

The script restarts the CR8 pair (core0 keeps the normal demo image), floods core1 with echoes
and prints one status line per run; the `w<N>` words are described at the top of
`exp_nested_yield.c`. A faulted core is recovered by restarting the pair, which the script does at
its start. The logs of the runs above are in [results/](results/).

The echo client on the Linux side is not part of this repository. The script runs the binary named
by `CLIENT` in the directory `BENCH` with the number of messages as its argument, and takes a line
of the form `N/N ok, 0 errors` as success; any rpmsg client that keeps sending to the core1 echo
endpoint and waits for each reply will produce the interrupt load. For the ordinary-application
runs our client was given a 5 ms pause between sends (200 messages per second). The verdict on
the firmware does not depend on the client: it is the black-box fault word and the `w<N>`
counters, read with `devmem`.
