# Building the CR8 firmware

`firmware/` is a reproducible build of the CR8 firmware family used by this project: an
e² studio base project plus small, asserted transforms that turn it into each variant, built
headless with the e² studio you already have installed.

## Layout

| Path | What |
|---|---|
| `base/` | The e² studio project inputs for **core0, per-core memory layout, PWM-demo functionality**: `.project`, `.cproject`, `configuration.xml` (RZ FSP 4.3.0), `src/`, `script/`. Generated content (`rz/`, `rzv_gen/`, `rzv_cfg/`, `Debug/`) is not tracked; the FSP generator recreates it at build time. Derived from the Renesas template `rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo` (BSD-3-Clause), migrated from RZ/V FSP 3.1.0 with `tools/migrate_cfg_430.py`. |
| `cm33_demo/` | The Renesas CM33 template project. The CR8 `.cproject` references its `.sbd` (interlock bundle), so it has to be in the same workspace; it is imported, and built once, alongside. |
| `variants/` | Anchored, asserted, idempotent transforms applied to a copy of `base/`. `common.py` holds the helpers; every edit names its anchor and fails loudly if the anchor is missing or ambiguous. |
| `tools/` | `build.sh` / `build.ps1`, `e2s_headless.sh`, `seed_pack_cache.py` (fills the per-user pack cache the generator reads), `patch_packs.py` (our FSP pack edits, below), `migrate_cfg_430.py` (3.1.0 → 4.3.0 project migration), `check_regen.py`, `patch-elf-phdr.py`, `null_phdr_at.py`, `deploy.sh`, `verify_elf.py`; `tools/board/` are the board-side scripts (`start-cr8.sh`, `start-cr8-core1.sh`, `restart-r8-pair.sh`, `bb.py`). |
| `extra/` | Sources not compiled by default: `r8_sensors.c` (GPS/compass task), `r8_uart_demo.c` + `r8_uart_proto.h` (core1 UART demo), `plane_remote/` (A55 web/gamepad remote for the fixed-wing bench). |
| `ref/` | md5 sums of historical reference binaries, for `verify_elf.py`. |

## Variants

```
bash tools/build.sh <variant>        # -> out/<variant>.elf (+ .map, .md5, build log)
```

| Variant | Core / layout | Contents |
|---|---|---|
| `core0-pwm` | core0, per-core (EVK) | rpmsg echo + PWM control + black box |
| `core0-pwm-shared` | core0, legacy shared layout (RDK device tree) | same firmware |
| `core0-pwm-plane` | core0, per-core (EVK) | `core0-pwm` reduced to 4 outputs on Pmod CN2 pins 7–10 (P74 = GPT4.A, P75 = GPT4.B, PA6 = GPT7.A, PA4 = GPT6.A), pulse clamp 1000–2000 µs / 50–400 Hz, duty 0 = forced low |
| `core0-demo` | core0, per-core (EVK) | `core0-pwm-plane` + `src/demo_servo.c`: angle sweep on CN2 pin 8 with a planted 16-bit overflow, built `-O0`; the firmware used by the debugging demo |
| `core1-echo` | core1, per-core | echo + black box, touches no shared peripheral |
| `core1-uart` | core1, per-core | `core1-echo` + RSCI5 UART demo (P72/P73) |

## What `build.sh` does

1. `rm -rf build/<variant>` and copy `base/` there. **Edits made in `build/<variant>` are
   lost on the next `build.sh`**; edit `base/` (or a variant script), or build the project in
   place from the e² studio GUI (Project → Build Project) and deploy with
   `e2studio/cr8-redeploy.sh`.
2. Apply the variant transform(s).
3. `seed_pack_cache.py`, then `patch_packs.py`. The 2026-10 generator does not read the packs
   from `<e2studio>/internal/projectgen/rz_fsp/packs` but from the per-user cache
   `~/.eclipse/com.renesas.platform_<id>/internal/projectgen/rz_fsp/` (`packs/`, `modules/`,
   `<ver>/devices|pinconfig|pinmapping|linkerscripts`, also under `rzv/`), which only a GUI
   start fills; on a headless-only host every component then fails with "Failed to locate
   component … in any software packs". `seed_pack_cache.py` mirrors the install into the cache
   (idempotent). `patch_packs.py` then makes sure every copy of the packs carries our patches
   (idempotent; keeps `<pack>.orig`). **Patch the packs, not the project's `rz/`** — the
   generator overwrites `rz/` from the packs on every build, and `check_regen.py` fails the
   build if a pack patch did not land.
4. Headless e² studio (`e2s_headless.sh`): fresh temporary workspace, imports `cm33_demo` and
   the variant, builds both `Debug` configurations, `-no-indexer`, log-idle detection and a
   hard timeout so a stuck dialog cannot hang the build forever. About 25 s on a desktop
   machine once the packs are warm.
5. `check_regen.py`: the generator really regenerated (tick channel in `vector_data.c`,
   every `g_gpt<N>` in `hal_data.c`, pins in `pin_data.c`, pack patches present in `rz/`).
6. `patch-elf-phdr.py`: zero-filesize DDR `PT_LOAD` segments become `PT_NULL`, otherwise
   remoteproc rejects the ELF with `-22`. Core1 variants additionally get
   `null_phdr_at.py 0x081BFFFC` (the cross-core init word lives in core0's SRAM).

Environment: `E2STUDIO` (default `~/rzv-tools/e2studio`; e² studio 2026-10 with RZ FSP 4.3.0),
`CM33_PROJECT` (default `firmware/cm33_demo`), `TC` (GNU Arm toolchain `bin` dir; default = the
one bundled with e² studio). On Windows, `tools\build.ps1 <variant>` does the same and finds the
newest `C:\Renesas\rzv\e2studio_*` (or `-E2Studio <dir>`).

## Moving a project from RZ/V FSP 3.1.0 to RZ FSP 4.3.0

`tools/migrate_cfg_430.py <project dir>` rewrites `configuration.xml` and `.cproject` in place
and then checks every module, config, property, option value and pack name it wrote against the
ids the installed 4.3.0 packs declare (it exits 1 on anything unknown). It covers what the
unified RZ FSP changed: component groups `all` → `rzv`, every RZ/V module / config / property id
gains an `rzv.` segment (`module.driver.timer_on_gpt` → `module.driver.rzv.timer_on_gpt`,
`config.driver.gpt` → `config.driver.rzv.gpt`, `config.bsp.rz.cr8` → `config.bsp.rzv.cr8`), the
three OpenAMP components become one `Linaro / library / OpenAMP-freertos`, two FreeRTOS
properties disappeared, and the FSP tree is `rz/` (`rzv_gen/` and `rzv_cfg/` keep their names) with the Cortex-R
port under `rm_freertos_port/cr8/`. Renesas publishes its own migrator for the same step
([renesas/rz-fsp#17](https://github.com/renesas/rz-fsp/issues/17), up to 4.2.0, then the
configurator's BSP tab for 4.3.0); this script exists so the build needs no manual configurator
session. The variant transforms (`variants/*.py`) anchor on the 4.3.0 ids.

Deploy: `bash tools/deploy.sh <evk-ip> out/core0-demo.elf --core 0 --name cr8_demo.elf --pw <password>`
copies the ELF to `/lib/firmware` and restarts the core through `tools/board/start-cr8.sh`.
**Stop OpenOCD first** if it is running (see the rules in the [README](../README.md)).
`e2studio/cr8-redeploy.sh` does the whole sequence in the right order.

## FSP pack patches (`tools/patch_packs.py`)

The edits are anchored in-place text transforms on the files inside the installed 4.3.0 packs
(`Renesas.RZV.4.3.0.pack`, `Linaro.OpenAMP-freertos.4.3.0.pack`); no FSP file is copied into
this repository any more. `patch_packs.py --diff --check` prints exactly what would change;
every edit is idempotent and refuses a file it does not recognise (the 3.1.0 handler, for one).

| File (in the pack) | Edit |
|---|---|
| `rz/fsp/src/rm_freertos_port/cr8/portASM.asm` | Interrupt-nesting count. 4.3.0 fixed the two findings of [renesas/rz-fsp#3](https://github.com/renesas/rz-fsp/issues/3) (`PUSH/POP {r0-r4, lr}` around the three `BLX`, `BIC sp, sp, #7` before `vTaskSwitchContext`), but `IRQ_Handler` still decides on `switch_before_exit` from `ulPortYieldRequired` alone. An inner (nested) interrupt whose ISR requests a yield therefore switches context while the outer ISR is still in progress: `portSAVE_CONTEXT` records the outer handler's SVC-mode state as the task's and the outer interrupt stays active in the GIC until that task runs again. The edit restores upstream FreeRTOS' ARM_CRx bookkeeping: `ulPortInterruptNesting++` after `PUSH {r0-r4, r12}`, `--` after the alignment word is popped, and `BNE exit_without_switch` when it is not 0 (the yield stays pending for the outermost handler). Nothing else in the 4.3.0 handler is touched. Not yet reported upstream. |
| `rz/fsp/src/rm_freertos_port/cr8/port.c` | Definition of `ulPortInterruptNesting`; weak `r8_tick_probe()` called at the top of `SysTick_Handler` (black box: tick liveness / jitter); weak `r8_irq_guard()` and a nested-yield counter after `bsp_common_interrupt_handler()` returns (observation only). |
| `rz/fsp/src/bsp/mcu/all/cr/bsp_irq.c` | Bounds check on the vector-table index before dispatch (ICCIAR 876 was once dispatched through a neighbouring object); weak `r8_nest_probe()` / `r8_bad_intid()`. |
| `rz/linaro/libmetal/include/metal/atomic.h` | `atomic_thread_fence` / `atomic_signal_fence` → `dmb sy`: the CR8 is outside the A55's Inner Shareable domain, `dmb ish` gives no cross-core visibility on the vrings. |
| `rz/linaro/open-amp/lib/rpmsg/rpmsg_virtio.c` | Weak boot-stage probes 0x50–0x55 around `rpmsg_virtio_wait_remote_ready()` and `virtio_create_virtqueues()` in `rpmsg_init_vdev_with_config()`. **Send-path doorbell:** after `virtqueue_kick(rvdev->svq)` the device side rings the doorbell itself when the kick was suppressed by `VRING_AVAIL_F_NO_INTERRUPT`. The 4.3.0 open-amp is role-aware and honours that flag; the user-space hosts on the A55 (the Renesas rpmsg samples and anything linked against the same older `libopen_amp`) are not: their `virtqueue_disable_cb()` sets the flag on every queue, yet they block on the MHU interrupt for each message. The 3.x device code never looked at the flag. Without the edit the name-service announcement sits unseen until the host's 15 s poll timeout. Buffer returns still honour the flag, so the doorbell count per message is unchanged from 3.1.0 (one). |

Dropped with 4.3.0: the 3.1.0 `portASM.asm` whole-file replacement (its `lr`/alignment part is
upstream now) and the libmetal `mutex.h` spin-then-block edit (4.3.0 ships a newer libmetal
whose FreeRTOS mutex blocks on `xSemaphoreTake(…, portMAX_DELAY)`, which is what the edit
emulated; the black box's `mtx_block` counter therefore stays at 0). The 4.3.0 open-amp is a
newer upstream too (`rpmsg_init_vdev_with_config`, `virtio_create_virtqueues`), which is why the
probes are anchored on those names. `check_regen.py` verifies after every build that the
generated `rz/` tree carries every edit and that `portASM.asm` is the 4.3.0 handler.

`patch_packs.py` always starts from the pristine archive (`<pack>.orig`), so an edit that changed
between versions of the script replaces its old output instead of stacking on it, and it only
touches `*.4.*.pack` files (the cache of an older RZ/V FSP 3.x install is left alone).

### What 4.3.0 changed for the application sources (`base/src`, `cm33_demo/src`)

RZ FSP 4.3.0 ships a much newer open-amp / libmetal than RZ/V FSP 3.1.0. The template sources
needed these ports; all of them are in the tree, listed here because each one cost a debugging
session and none of them is in the Renesas migration guide:

| Where | Change | Symptom without it |
|---|---|---|
| `rsc_table.h` | `RSC_RPROC_MEM` (type 4) and `struct fw_rsc_rproc_mem` are defined locally: they were a Renesas addition to the old open-amp and are gone upstream. The entry stays in the resource table (same bytes; the new parser skips unknown types). | does not compile |
| `main_task_entry.c` | `VIRTIO_DEV_SLAVE` → `VIRTIO_DEV_DEVICE`. | does not compile |
| `rzv2_rproc.c` | `remoteproc_ops.init` takes a `const` ops pointer; `metal_irq_register()` / `metal_irq_unregister()` are no longer called: the 4.3.0 MHU driver dispatches `R_MHU_B_NS_IsrSub()` itself through `metal_irq_handle()`, and libmetal's IRQ API now needs an IRQ controller this port does not register. | does not compile |
| `configuration.xml` | `configUSE_MUTEXES` enabled: libmetal's `metal_mutex` is now a FreeRTOS mutex (`migrate_cfg_430.py` sets it). | link error `xSemaphoreCreateMutex` |
| `platform_info.c` (create) | `gfeatures` in the resource table is seeded with `dfeatures` when it is 0. The new device side uses `dfeatures & gfeatures`; the older A55 hosts never write `gfeatures`, so `VIRTIO_RPMSG_F_NS` came out "not negotiated" and no name-service announcement was sent. | host waits for the endpoint forever |
| `platform_info.c` (release) | the `virtio_device` pointer is taken before `rpmsg_deinit_vdev()`, which now clears `rvdev->vdev` and frees the virtqueues. Passing the cleared pointer made `remoteproc_remove_virtio()` a no-op; the next `remoteproc_create_virtio()` returned the stale device and its virtqueues were freed a second time. | `heap_4` assert in `vPortFree` (seen as a prefetch abort: the assert is a `bkpt`) on the second host connection |
| pack edit above | send-path doorbell. | first message arrives after 15 s |

The FreeRTOS port files are MIT (Amazon), `bsp_irq.c` is BSD-3-Clause (Renesas), libmetal and
open-amp are BSD-3-Clause; the edits are applied to the user's locally installed packs, see
[NOTICE.md](../NOTICE.md). (Up to v1.0.1 the repository referenced copies of the patched files in
`firmware/fsp-patches/rzv/`; that directory was never tracked because `.gitignore` ignores every
`rzv/` tree, so a fresh clone could not build. The in-script edits close that gap.)

## Rules that are easy to forget

* **Verify regeneration** after touching `configuration.xml`; a module added by hand also
  needs its `<stack>` entry or it is silently skipped (`variants/core1_uart.py` shows the
  pattern). FSP needs a module to be removed in three places (module, stack, pincfg).
* **A core that has run must not be restarted alone while the other R8 runs** (no per-core
  reset on the CR8 cluster). `deploy.sh --pair` / `restart-r8-pair.sh` do the
  stop-both → core0 → core1 sequence.
* **One rpmsg client per channel.** Two clients on the same vring corrupt it.
* Shared-layout firmware (`core0-pwm-shared`) only pairs with the legacy A55 client (RDK);
  per-core firmware only with the per-core clients (EVK).
* `dmb ish` remains inside `metal_io_read/write` and `rpmsg_virtio_*` (seq_cst atomics
  inlined by GCC); the fence-macro override in the pack patches covers the rest.
  `verify_elf.py` reports the barrier census and fails only if it gets worse than the
  reference.
* A project still on RZ/V FSP 3.1.0 must go through `tools/migrate_cfg_430.py` first; the
  4.3.0 generator does not migrate `configuration.xml` on its own (headless it fails with
  "Failed to locate component … V3.1.0").

## Debugging your own project

Any firmware that runs on the CR8 can be debugged the same way. Build it with `-g` (and
`-O0`/`-Og` where you want to see every local), make sure the ELF on the board is the one
e² studio loads symbols from, then:

1. Copy `e2studio/CR8 core0 via OpenOCD dmem.launch` into your project and adjust
   `PROGRAM_NAME`/`PROJECT_ATTR` if the names differ.
2. Main tab: *Build before launching* = **Disable auto build** (a rebuild would change the
   ELF under the running firmware). Debugger tab: `gdb-multiarch`, Generic TCP/IP,
   connection `localhost:3333`. The launch never loads or resets anything; remoteproc owns
   the firmware.
3. Breakpoints are hardware breakpoints (6 per core); Eclipse sets them as such
   automatically. Prefer Step Over; the config masks interrupts during steps.

Building this project from the e² studio GUI (instead of `tools/build.sh`) has not been
exercised end to end; the headless build uses the same managed-build configuration, so it is
expected to work.
