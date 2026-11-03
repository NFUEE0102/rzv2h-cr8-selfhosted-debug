/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include <stdio.h>
#include "hal_data.h"

#if BSP_FEATURE_BSP_SUPPORT_STARTING_CR8

 #include "cr8_start.h"

/* Macro to set bits of CGC_CR8_0_PERIPHCLK, CGC_CR8_0_ACLK, CGC_CR8_0_ATCLK0 */
 #define CR8_PRV_CPG_CLKON_0_VALUE                         ((7U <<                                \
                                                             R_CPG_CPG_CLKON_0_CLK13_ONWEN_Pos) | \
                                                            (7U << R_CPG_CPG_CLKON_0_CLK13_ON_Pos))

/* Macro to set bits of CGC_CR8_0_TSCLK, CGC_CR8_0_DBGCLK */
 #define CR8_PRV_CPG_CLKON_1_VALUE                         ((3U <<                               \
                                                             R_CPG_CPG_CLKON_1_CLK0_ONWEN_Pos) | \
                                                            (3U << R_CPG_CPG_CLKON_1_CLK0_ON_Pos))

/* Macro to confirm bits of CGC_CR8_0_PERIPHCLK, CGC_CR8_0_ACLK, CGC_CR8_0_ATCLK0, CGC_CR8_0_TSCLK, CGC_CR8_0_DBGCLK */
 #define CR8_PRV_CPG_CLKMON_0_VALUE                        ((3U <<                               \
                                                             R_CPG_CPG_CLKMON_0_CLK16_MON_Pos) | \
                                                            (7U << R_CPG_CPG_CLKMON_0_CLK13_MON_Pos))

/* Macro to confirm bits of CR8_0_NCPURESET[0] to CR8_0_NTSRESET */
 #define CR8_PRV_CPG_RSTMON0_VALUE                         (0xFFF00000U)

/* Macro to confirm a bit of CR8_0_NMISCRESET */
 #define CR8_PRV_CPG_RSTMON1_VALUE                         (0x00000001U)

/* Macro to set a bit of CR8_0_NMISCRESET */
 #define CR8_PRV_CPG_RST_2_NMISCRESET_VALUE                ((1U << R_CPG_CPG_RST_2_RSTB12_WEN_Pos) | \
                                                            (1U << R_CPG_CPG_RST_2_RSTB12_Pos))

/* Macro to set bits of CR8_0_NCPURESET[0] to CR8_0_NTSRESET */
 #define CR8_PRV_CPG_RST_2_ASSERT_RESET_OTHERCR8_VALUE     ((0x1FFFU <<                       \
                                                             R_CPG_CPG_RST_2_RSTB0_WEN_Pos) | \
                                                            (0x0000U << R_CPG_CPG_RST_2_RSTB0_Pos))

 #define CR8_PRV_CPG_RST_2_RELEASE_RESET_OTHERCR8_VALUE    ((0x1FFFU <<                       \
                                                             R_CPG_CPG_RST_2_RSTB0_WEN_Pos) | \
                                                            (0x1FFFU << R_CPG_CPG_RST_2_RSTB0_Pos))

 #define CR8_PRV_CPG_LP_CR8_CTL4_POWERUP_ACT_FINISHED      (0U << R_CPG_CPG_LP_CR8_CTL4_POWERUP_ACT_Pos)
 #define CR8_PRV_CPG_LP_CR8_CTL4_CLR_RESET_TRG             (0U << R_CPG_CPG_LP_CR8_CTL4_RESET_TRIG_Pos)

void release_reset_cr8 (void)
{
    /* Assert CR8 resets to keep the initial state constant. */
    R_CPG->CPG_RST_2 = CR8_PRV_CPG_RST_2_ASSERT_RESET_OTHERCR8_VALUE;

    /* Turn on the clock related to CR8 */
    R_CPG->CPG_CLKON_0 = CR8_PRV_CPG_CLKON_0_VALUE;
    R_CPG->CPG_CLKON_1 = CR8_PRV_CPG_CLKON_1_VALUE;

    FSP_HARDWARE_REGISTER_WAIT((CR8_PRV_CPG_CLKMON_0_VALUE & R_CPG->CPG_CLKMON_0), CR8_PRV_CPG_CLKMON_0_VALUE);

    /* Setting CR8 bus master access attributes as non-secure and non-privileged. */
    R_BSP_MASTER_ACCESS_CONTROL_SET(MST_ACCCNT_CR8_0,
                                    BSP_MST_ACCCNT_LEVEL_NONPRIVILEGED_NONSECURE,
                                    BSP_MST_ACCCNT_WRITE_DIRECTION);
    R_BSP_MASTER_ACCESS_CONTROL_SET(MST_ACCCNT_CR8_0,
                                    BSP_MST_ACCCNT_LEVEL_NONPRIVILEGED_NONSECURE,
                                    BSP_MST_ACCCNT_READ_DIRECTION);
    R_BSP_MASTER_ACCESS_CONTROL_SET(MST_ACCCNT_CR8_1,
                                    BSP_MST_ACCCNT_LEVEL_NONPRIVILEGED_NONSECURE,
                                    BSP_MST_ACCCNT_WRITE_DIRECTION);
    R_BSP_MASTER_ACCESS_CONTROL_SET(MST_ACCCNT_CR8_1,
                                    BSP_MST_ACCCNT_LEVEL_NONPRIVILEGED_NONSECURE,
                                    BSP_MST_ACCCNT_READ_DIRECTION);
    R_BSP_MASTER_ACCESS_CONTROL_SET(MST_ACCCNT_CR8_LLPP,
                                    BSP_MST_ACCCNT_LEVEL_NONPRIVILEGED_NONSECURE,
                                    BSP_MST_ACCCNT_WRITE_DIRECTION);
    R_BSP_MASTER_ACCESS_CONTROL_SET(MST_ACCCNT_CR8_LLPP,
                                    BSP_MST_ACCCNT_LEVEL_NONPRIVILEGED_NONSECURE,
                                    BSP_MST_ACCCNT_READ_DIRECTION);

    /* 1: Confirm CR8 is reset state now */
    FSP_HARDWARE_REGISTER_WAIT((CR8_PRV_CPG_RSTMON0_VALUE & R_CPG->CPG_RSTMON_0), CR8_PRV_CPG_RSTMON0_VALUE);

    FSP_HARDWARE_REGISTER_WAIT((CR8_PRV_CPG_RSTMON1_VALUE & R_CPG->CPG_RSTMON_1), CR8_PRV_CPG_RSTMON1_VALUE);

    /* 2: Enable CR8 interrupt request output bits of CPG_LP_CR8_CTL3 */
    R_CPG->CPG_LP_CR8_CTL3 =
        (R_CPG_CPG_LP_CR8_CTL3_CSYSREQ_TS_Msk | R_CPG_CPG_LP_CR8_CTL3_CSYSREQ_DBG_Msk |
         R_CPG_CPG_LP_CR8_CTL3_CSYSREQ_ATB1_INST_Msk | R_CPG_CPG_LP_CR8_CTL3_CSYSREQ_ATB1_DATA_Msk |
         R_CPG_CPG_LP_CR8_CTL3_CSYSREQ_ATB0_INST_Msk | R_CPG_CPG_LP_CR8_CTL3_CSYSREQ_ATB0_DATA_Msk);

    /* 3: Clear CPG_CR8_CONFIG1.CPUHALT bits (Disable fetch) */
    R_CPG->CPG_CR8_CONFIG1 = 0x00000000;

    /* 4: Release reset of CPG_RST_2.CR8_0_NMISCRESET */
    R_CPG->CPG_RST_2 = CR8_PRV_CPG_RST_2_NMISCRESET_VALUE;

    /* 5: Wait until release reset sequence execution available */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_LP_CR8_CTL4_RESET_CTRL_READY_Msk & R_CPG->CPG_LP_CR8_CTL4),
                               R_CPG_CPG_LP_CR8_CTL4_RESET_CTRL_READY_Msk);

    /* 6: Write CPG_LP_CR8_CTL4.RESET_TRIG bit */
    R_CPG->CPG_LP_CR8_CTL4 = R_CPG_CPG_LP_CR8_CTL4_RESET_TRIG_Msk;

    /* 7: Wait until Reset release request received */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_LP_CR8_CTL4_RESET_RELEASEREQ_Msk & R_CPG->CPG_LP_CR8_CTL4),
                               R_CPG_CPG_LP_CR8_CTL4_RESET_RELEASEREQ_Msk);

    /* 8: Release all of CR8 reset bits in CPG_RST_2 */
    R_CPG->CPG_RST_2 = CR8_PRV_CPG_RST_2_RELEASE_RESET_OTHERCR8_VALUE;

    /* 9: Wait until Reset release sequence finished */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_LP_CR8_CTL4_POWERUP_ACT_Msk & R_CPG->CPG_LP_CR8_CTL4),
                               CR8_PRV_CPG_LP_CR8_CTL4_POWERUP_ACT_FINISHED);

    /* 10: Clear CPG_LP_CR8_CTL4.RESET_TRIG bit */
    R_CPG->CPG_LP_CR8_CTL4 = CR8_PRV_CPG_LP_CR8_CTL4_CLR_RESET_TRG;

    /* Load CR8 dummy program to ITCM0, ITCM1 */
    copy_cr8_prog();

    /* 12: Set CPG_CR8_CONFIG1.CPUHALT bits (Enable fetch) */
    R_CPG->CPG_CR8_CONFIG1 = R_CPG_CPG_CR8_CONFIG1_nCPUHALT_Msk;
}

#endif
