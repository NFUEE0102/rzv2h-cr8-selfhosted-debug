/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#ifndef PLL_INIT_H_
#define PLL_INIT_H_

/* generic headers */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "hal_data.h"

/* Initial values for CA55 1.8GHz */
#define CPG_PLLCA55_CLK1_1_8GHZ     (0x00002582)
#define CPG_PLLCA55_CLK2_1_8GHZ     (0x000c1e00)

/* Initial values for CA55 1.7GHz */
#define CPG_PLLCA55_CLK1_1_7GHZ     (0x80003543)
#define CPG_PLLCA55_CLK2_1_7GHZ     (0x000c1e00)

#define CPG_PLLDSI_CLK1_INITVAL     (0x00003182)
#define CPG_PLLDSI_CLK2_INITVAL     (0x000C1803)

#define CPG_PLLGPU_CLK1_INITVAL     (0x00003482)
#define CPG_PLLGPU_CLK2_INITVAL     (0x00001A01)

#define CPG_PLLDRP_CLK1_INITVAL     (0x00003482)
#define CPG_PLLDRP_CLK2_INITVAL     (0x000C1A01)

/*
 * function declarations
 */
void pll_init_cm33boot(void);
void pll_init_other(void);
void pll_reboot_ca55_at_1_8GHz(void);

#endif                                 /* PLL_INIT_H_ */
