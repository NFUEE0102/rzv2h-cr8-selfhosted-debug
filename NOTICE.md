# Third-party notices

Our own code and documentation are BSD-3-Clause (see [LICENSE](LICENSE)). The repository
redistributes or modifies the following third-party material.

| Component | Where | License | Copyright |
|---|---|---|---|
| Renesas e² studio template projects (`rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo`, `rzv2h_rdk_cm33_rpmsg_linux_rtos_demo`), migrated to RZ FSP 4.3.0 | `firmware/base/`, `firmware/cm33_demo/` | BSD-3-Clause (SPDX headers in the files) | Renesas Electronics Corporation and/or its affiliates, 2020–2024 |
| Edits to files inside the user's installed RZ FSP 4.3.0 packs, applied locally at build time by `firmware/tools/patch_packs.py` (the script holds only the inserted lines and their anchors, not the files): `bsp_irq.c` (BSD-3-Clause, Renesas); `portASM.asm`, `port.c` of the FreeRTOS Cortex-R8 port (MIT, Amazon.com, Inc., FreeRTOS Kernel V10.4.3 LTS Patch 2); libmetal `atomic.h` and open-amp `rpmsg_virtio.c` (BSD-3-Clause, Xilinx Inc., Nordic Semiconductor ASA, Linaro and other OpenAMP contributors) | `firmware/tools/patch_packs.py` | as listed | as listed |
| OpenAMP and libmetal (used by the template projects through FSP; only our configuration and edits live here) | `firmware/base/src/` (`platform_info.c`, `rsc_table.c`, `rzv2_rproc.c`, …) | BSD-3-Clause | Xilinx Inc., Linaro, and other OpenAMP contributors |
| OpenOCD patch (one `ISB` before restart in `cortex_a_internal_restart()`) | `debug/openocd-isb-before-restart.py`, `debug/build-openocd.sh` | GPL-2.0-or-later (OpenOCD's license; the patch is a modification of OpenOCD) | OpenOCD contributors |
| OpenOCD prebuilt binary `openocd-rzv2h-aarch64.tar.gz` (GitHub Releases only, not in the repository) | Releases | GPL-2.0-or-later | OpenOCD contributors. Built from upstream commit `1f68633` (https://github.com/openocd-org/openocd) plus the patch above; the complete corresponding source is that commit with `debug/openocd-isb-before-restart.py` applied, as done by `debug/build-openocd.sh`. Dynamically linked against Jim Tcl (`libjim`, BSD-2-Clause) from the Ubuntu 24.04 package. |
| OpenOCD configuration (`cr8-dmem.cfg`) follows the structure of the TI K3 `dmem` board files shipped with OpenOCD | `debug/cr8-dmem.cfg` | GPL-2.0-or-later (OpenOCD tcl scripts) | Texas Instruments Incorporated, OpenOCD contributors |

Not included: any Renesas proprietary binary (DRP-AI, codec, e² studio itself, FSP packs).
Users install e² studio and the RZ/V FSP pack from Renesas under Renesas' terms; our
`tools/patch_packs.py` modifies the locally installed pack files (and keeps `.orig` copies).

Hardware register facts quoted in `docs/` come from the Renesas *RZ/V2H Group User's Manual:
Hardware* (R01UH1032EJ0130); the manual itself is not redistributed.

## Renesas Multi-OS package sample files (restricted sample licence)

Six files carry the Renesas sample-code header ("may only be used with products of Renesas
Electronics Corp. ... No other uses are authorized"), with co-copyright eForce Co., Ltd.:

- `firmware/base/src/OpenAMP_RPMsg_cfg.h`, `rpmsg_demo.c`, `rsc_table.c`, `rsc_table.h`, `sys_init.c`
- `firmware/cm33_demo/src/platform_info.h`

They originate from the Renesas RZ/V2H Multi-OS Package (the RDK template projects are
built from it). Renesas support confirmed in November 2026 that redistributing them in a
public repository is fine as long as the original source is credited, which this file does.
Renesas itself publishes the same template projects on GitHub, in the `renesas-rdk`
organisation, as public repositories without a separate LICENSE file:

- https://github.com/renesas-rdk/rzv2h_rdk_cr8_core0_rpmsg_linux_rtos_demo (`src/OpenAMP_RPMsg_cfg.h`, `rpmsg_demo.c`, `rsc_table.c`, `rsc_table.h`, `sys_init.c`)
- https://github.com/renesas-rdk/rzv2h_rdk_cm33_rpmsg_linux_rtos_demo (`src/platform_info.h`)

Our `rsc_table.c` and `sys_init.c` are byte-identical to those; `OpenAMP_RPMsg_cfg.h`,
`rsc_table.h` and `platform_info.h` differ only in configuration values / line endings, plus,
in `rsc_table.h`, a local definition of `RSC_RPROC_MEM` / `struct fw_rsc_rproc_mem` (a Renesas
resource type that the open-amp shipped with RZ FSP 4.3.0 no longer declares);
`rpmsg_demo.c` carries our additions (the demo's status words and the black-box hooks). The
Renesas headers are kept unchanged and the files are used only with the RZ/V2H, as the header
requires. They are NOT covered by this repository's BSD-3-Clause licence: Renesas' header text
applies to them. If you prefer not to redistribute them at all, delete the five `firmware/base/src`
files and `firmware/cm33_demo/src/platform_info.h` and copy them from the two repositories above
before building.
