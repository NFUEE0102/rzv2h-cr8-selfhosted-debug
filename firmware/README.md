# firmware/ — RZ/V2H Cortex-R8 firmware, built headless from e² studio projects

The CR8 firmware family of this repository (rpmsg echo + PWM control + black box on core0,
echo/UART on core1, and the debugging demo), built from `base/` with asserted variant
transforms and a headless e² studio. Full description: [docs/build-firmware.md](../docs/build-firmware.md).

## Quickstart (Linux, e² studio 2026-10 + RZ FSP 4.3.0 installed, default `~/rzv-tools/e2studio`; Windows: `tools\build.ps1 <variant>`)

```bash
python3 tools/patch_packs.py --e2studio ~/rzv-tools/e2studio     # once per e² studio install (idempotent, keeps <pack>.orig)
bash tools/build.sh core0-demo                                   # -> out/core0-demo.elf (+ .map, .md5, build log), ~25 s
bash tools/deploy.sh <evk-ip> out/core0-demo.elf --core 0 --name cr8_demo.elf --pw <password>
```

`build.sh` recreates `build/<variant>/` from `base/` every time, applies the variant,
verifies the FSP packs are patched, runs e² studio headless (a fresh temporary workspace,
`-no-indexer`, stuck-dialog detection), checks that the generator really regenerated, and
post-processes the ELF for remoteproc. Stop OpenOCD on the board before `deploy.sh`.

## Layout

| Path | What |
|---|---|
| `base/` | e² studio project inputs for core0, per-core layout, PWM-demo functionality. Generated content (`rzv/`, `rzv_gen/`, `rzv_cfg/`, `Debug/`) is not tracked. |
| `cm33_demo/` | Renesas CM33 template project; the CR8 `.cproject` references its `.sbd`, so it is imported alongside. |
| `variants/` | Anchored, asserted, idempotent transforms applied to a copy of `base/`: `layout_shared.py`, `core0_pwm_plane.py`, `core0_demo.py`, `core1_echo.py`, `core1_uart.py`; `files/demo_servo.c`. |
| `tools/patch_packs.py` | Our FSP 4.3.0 pack edits, as anchored in-place text transforms (no copied FSP files): `portASM.asm` (interrupt-nesting count: no context switch from a nested IRQ exit), `port.c` (weak `r8_tick_probe()` / `r8_irq_guard()` hooks), `bsp_irq.c` (vector-table bounds check), libmetal `atomic.h` (`dmb sy`), open-amp `rpmsg_virtio.c` (boot-stage probes). `--diff` prints what it changes. |
| `tools/migrate_cfg_430.py` | The RZ/V FSP 3.1.0 → RZ FSP 4.3.0 migration of `configuration.xml` / `.cproject` (applied once to `base/` and `cm33_demo/`; kept for projects still on 3.1.0). |
| `tools/seed_pack_cache.py` | Fills the per-user pack cache (`~/.eclipse/com.renesas.platform_*/internal/projectgen/rz_fsp/`) the 2026-10 generator reads; a headless-only host never gets it from the GUI. Run by `build.sh` / `build.ps1`. |
| `extra/` | Not compiled by default: `r8_sensors.c` (GPS/IST8310 task), `r8_uart_demo.c` + `r8_uart_proto.h` (core1 UART demo), `plane_remote/` (A55 web/gamepad remote). |
| `tools/` | Build/verify/deploy tooling; `tools/board/` = board-side start/deploy/black-box scripts. |
| `ref/` | md5 of historical reference binaries for `verify_elf.py`. |

## Variants (`tools/build.sh <variant>`)

| variant | core / layout | contents |
|---|---|---|
| `core0-pwm` | core0, per-core (EVK) | rpmsg echo + PWM control + black box |
| `core0-pwm-shared` | core0, shared/legacy (RDK DT) | same firmware |
| `core0-pwm-plane` | core0, per-core (EVK) | 4 outputs on Pmod CN2 pins 7–10 (P74 GPT4.A, P75 GPT4.B, PA6 GPT7.A, PA4 GPT6.A), pulse clamp 1000–2000 µs / 50–400 Hz, duty 0 = forced low |
| `core0-demo` | core0, per-core (EVK) | `core0-pwm-plane` + `demo_servo.c` (angle sweep on CN2 pin 8, planted 16-bit overflow, `-O0`) — the debugging demo |
| `core1-echo` | core1, per-core | echo + black box |
| `core1-uart` | core1, per-core | + RSCI5 UART demo (P72/P73) |

## Rules that are easy to forget

* **Patch the packs, not the project's `rz/`** — the generator overwrites `rz/` from the
  packs. `check_regen.py` fails the build if a pack patch did not land.
* **Verify regeneration** after touching `configuration.xml`; a module added by hand also
  needs its `<stack>` entry or it is silently skipped (`variants/core1_uart.py` shows the
  pattern).
* **A core that has run must not be restarted alone while the other R8 runs** (no per-core
  reset). `deploy.sh --pair` does the stop-both → core0 → core1 dance via `restart-r8-pair.sh`.
* **One rpmsg client per channel.** Stop any daemon holding the channel before running
  another client by hand.
* Shared-layout firmware only pairs with the legacy client (RDK); per-core firmware only with
  the per-core clients (EVK).
* `dmb ish` remains inside `metal_io_read/write` and `rpmsg_virtio_*` (seq_cst atomics
  inlined by GCC); the fence macro override covers the rest. `verify_elf.py` reports the
  census and fails only if it gets worse than the reference.
