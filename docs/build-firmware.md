# Building the CR8 firmware

`firmware/` is a reproducible build of the CR8 firmware family used by this project: an
e² studio base project plus small, asserted transforms that turn it into each variant, built
headless with the e² studio you already have installed.

## Layout

| Path | What |
|---|---|
| `base/` | The e² studio project inputs for **core0, per-core memory layout, PWM-demo functionality**: `.project`, `.cproject`, `configuration.xml`, `src/`, `script/`. Generated content (`rzv/`, `rzv_gen/`, `rzv_cfg/`, `Debug/`) is not tracked; the FSP generator recreates it at build time. Derived from the Renesas template `rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo` (BSD-3-Clause). |
| `cm33_demo/` | The Renesas CM33 template project. The CR8 `.cproject` references its `.sbd` (interlock bundle), so it has to be in the same workspace; it is imported, and built once, alongside. |
| `variants/` | Anchored, asserted, idempotent transforms applied to a copy of `base/`. `common.py` holds the helpers; every edit names its anchor and fails loudly if the anchor is missing or ambiguous. |
| `fsp-patches/rzv/` | FSP 3.1.0 files with our fixes (below). `tools/patch_packs.py` injects them into the installed packs. |
| `tools/` | `build.sh`, `e2s_headless.sh`, `patch_packs.py`, `check_regen.py`, `patch-elf-phdr.py`, `null_phdr_at.py`, `deploy.sh`, `verify_elf.py`; `tools/board/` are the board-side scripts (`start-cr8.sh`, `start-cr8-core1.sh`, `restart-r8-pair.sh`, `bb.py`). |
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
3. `patch_packs.py`: make sure the installed FSP packs carry our patches (idempotent; keeps
   `<pack>.orig`). **Patch the packs, not the project's `rzv/`** — the generator overwrites
   `rzv/` from the packs on every build, and `check_regen.py` fails the build if a pack patch
   did not land.
4. Headless e² studio (`e2s_headless.sh`): fresh temporary workspace, imports `cm33_demo` and
   the variant, builds both `Debug` configurations, `-no-indexer`, log-idle detection and a
   hard timeout so a stuck dialog cannot hang the build forever. About 25 s on a desktop
   machine once the packs are warm.
5. `check_regen.py`: the generator really regenerated (tick channel in `vector_data.c`,
   every `g_gpt<N>` in `hal_data.c`, pins in `pin_data.c`, pack patches present in `rzv/`).
6. `patch-elf-phdr.py`: zero-filesize DDR `PT_LOAD` segments become `PT_NULL`, otherwise
   remoteproc rejects the ELF with `-22`. Core1 variants additionally get
   `null_phdr_at.py 0x081BFFFC` (the cross-core init word lives in core0's SRAM).

Environment: `E2STUDIO` (default `~/rzv-tools/e2studio`), `CM33_PROJECT` (default
`firmware/cm33_demo`), `TC` (GNU Arm toolchain `bin` dir; default = the one bundled with
e² studio).

Deploy: `bash tools/deploy.sh <evk-ip> out/core0-demo.elf --core 0 --name cr8_demo.elf --pw <password>`
copies the ELF to `/lib/firmware` and restarts the core through `tools/board/start-cr8.sh`.
**Stop OpenOCD first** if it is running (see the rules in the [README](../README.md)).
`e2studio/cr8-redeploy.sh` does the whole sequence in the right order.

## FSP patches (`fsp-patches/rzv/`)

| File | Fix |
|---|---|
| `portASM.asm` | `IRQ_Handler` did not save `lr_svc` across the nested call. With nested interrupts enabled (`configMAX_API_CALL_INTERRUPT_PRIORITY` lower than the highest used priority) the inner interrupt's `BLX` overwrote the outer handler's `lr`; on the way out the outer handler branched into its own epilogue and took a Data Abort. Fix: push/pop `lr` around the nested window. Verified over 5 hours / 681 nested events. |
| `port.c` | Weak `r8_tick_probe()` hook called from the tick handler (used by the black box to prove the tick is alive and to measure jitter). |
| `bsp_irq.c` | Bounds check on the vector-table index before dispatch. |

The FreeRTOS files are MIT (Amazon), `bsp_irq.c` is BSD-3-Clause (Renesas); see
[NOTICE.md](../NOTICE.md).

**Upstream status.** The `portASM.asm` and alignment findings were reported as
[renesas/rz-fsp#3](https://github.com/renesas/rz-fsp/issues/3) and are fixed in RZ FSP v4.3.0
(Renesas' version keeps `PUSH {r0-r4, r12}` and brackets the three `BLX` calls with
`PUSH/POP {r0-r4, lr}`, plus `BIC sp, sp, #7` on the SVC path — equivalent to this patch).
The replacement file stays in this repository until the project moves to 4.3.0; see the
README roadmap. The `port.c` hook and the libmetal / OpenAMP edits are ours and will be
re-anchored on the new pack, not dropped.

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
