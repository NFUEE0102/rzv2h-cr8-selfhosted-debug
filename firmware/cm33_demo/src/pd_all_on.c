/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include "i2c_pmic.h"
#include "pll_init.h"

/*******************************************************************************************************************//**
 * @addtogroup pd_all_on
 * @{
 **********************************************************************************************************************/

#if defined(BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT) && (BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT == 1)

/* Initialize value of CPG_CLMAn_CTL Registers */
 #define CPG_CLMA0_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA1_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA2_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA3_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA4_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA5_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA6_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA7_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA8_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA9_CTL_INITVAL                            (0x001F001FU)
 #define CPG_CLMA10_CTL_INITVAL                           (0x001F001FU)
 #define CPG_CLMA11_CTL_INITVAL                           (0x001F001FU)
 #define CPG_CLMA12_CTL_INITVAL                           (0x001F001FU)
 #define CPG_CLMA13_CTL_INITVAL                           (0x001F001FU)
 #define CPG_CLMA14_CTL_INITVAL                           (0x001F001FU)

/* Reset value of CPG resigters */
 #define CPG_OTHERS_INI_RESET                             (1U)
 #define CPG_OTHERS_INI_RELEASE_RESET                     (0U)

/* Setting value of PMU control registers */
 #define CPG_LP_PWC_CTL1_OTHER_POWER_ON_START             (1U)
 #define CPG_LP_PWC_CTL1_OTHER_POWER_ON_STOP              (0U)
 #define CPG_LP_PWC_CTL2_PWEN_PWEN0_HIGH                  (1U)
 #define CPG_LP_PWC_CTL2_PWEN_PWEN1_HIGH                  (2U)
 #define CPG_LP_PWC_CTL2_PWEN_PWEN2_HIGH                  (4U)
 #define CPG_LP_PWC_CTL2_PWEN_PWEN0_MASK                  (1U)
 #define CPG_LP_PWC_CTL2_PWEN_PWEN1_MASK                  (2U)
 #define CPG_LP_PWC_CTL2_PWEN_PWEN2_MASK                  (4U)
 #define CPG_LP_PMU_CTL1_DOMAIN_CTRL_REQ_OUTPUT           (1U)
 #define CPG_LP_PMU_CTL1_DOMAIN_CTRL_REQ_STOP             (0U)
 #define CPG_LP_PMU_CTL1_DOMAIN_ON_REQ                    (2U)
 #define CPG_LP_PMU_CTL1_DOMAIN_OFF_REQ                   (0U)
 #define CPG_LP_PMU_CTL1_DOMAIN_CTRL_PROGRESS             (4U)
 #define CPG_LP_PMU_CTL1_DOMAIN_CTRL_COMPLETE             (0U)
 #define CPG_LP_PMU_CTL1_DOMAIN_ON_COMPLETE               (8U)
 #define CPG_LP_PMU_CTL1_DOMAIN_OFF_COMPLETE              (0U)

/* Value of information of SRAM recovery handshake */
 #define CPG_OTP_HANDSHAKE_MON_COMPLETE                   (1U)
 #define CPG_OTP_HANDSHAKE_MON_PROGRESS                   (0U)

 #define CPG_BUS_10_MSTOP_INITVAL                         (0x04000000U)
 #define CPG_BUS_12_MSTOP_INITVAL                         (0x04000400U)

 #define CPG_RST_3_RELEASE_RESETVAL                       (0xFF00FF00U)
 #define CPG_RST_4_RELEASE_RESETVAL                       (0x003F003FU)

/* Initialize value of CPG_RST_n Registers */
 #define CPG_RST_0_INITVAL                                (0x3FFF0000U)
 #define CPG_RST_1_INITVAL                                (0x00070000U)
 #define CPG_RST_2_INITVAL                                (0x1FFF0000U)
 #define CPG_RST_3_INITVAL                                (0xE7BC0000U)
 #define CPG_RST_4_INITVAL                                (0x003F0000U)
 #define CPG_RST_5_INITVAL                                (0xFE800000U)
 #define CPG_RST_6_INITVAL                                (0x9E1F0000U)
 #define CPG_RST_7_INITVAL                                (0xF9DF0000U)
 #define CPG_RST_8_INITVAL                                (0xFFFF0000U)
 #define CPG_RST_9_INITVAL                                (0xFFDF0000U)
 #define CPG_RST_10_INITVAL                               (0x03860000U)
 #define CPG_RST_11_INITVAL                               (0x00040000U)
 #define CPG_RST_12_INITVAL                               (0xFFE00000U)
 #define CPG_RST_13_INITVAL                               (0xF1E10000U)
 #define CPG_RST_14_INITVAL                               (0xFFFF0000U)
 #define CPG_RST_15_INITVAL                               (0x71030000U)
 #define CPG_RST_16_INITVAL                               (0xFFFF0000U)
 #define CPG_RST_17_INITVAL                               (0x03FF0000U)

/* Initialize value of CPG_CLKON_n Registers */
 #define CPG_CLKON_0_INITVAL                              (0xFFDFFFDFU)
 #define CPG_CLKON_1_INITVAL                              (0xFFFBFFFBU)
 #define CPG_CLKON_2_INITVAL                              (0x80008000U)
 #define CPG_CLKON_3_INITVAL                              (0xFFFEFFFEU)
 #define CPG_CLKON_4_INITVAL                              (0x7FFF7FFFU)
 #define CPG_CLKON_5_INITVAL                              (0xFFF0FFF0U)
 #define CPG_CLKON_6_INITVAL                              (0xFFFFFFFFU)
 #define CPG_CLKON_7_INITVAL                              (0xFFFFFFFFU)
 #define CPG_CLKON_8_INITVAL                              (0x7FFF7FFFU)
 #define CPG_CLKON_9_INITVAL                              (0x7FFF7FFFU)
 #define CPG_CLKON_10_INITVAL                             (0xFFF8FFF8U)
 #define CPG_CLKON_11_INITVAL                             (0xFFFFFFFFU)
 #define CPG_CLKON_12_INITVAL                             (0xFFFFFFFFU)
 #define CPG_CLKON_13_INITVAL                             (0xFFFFFFFFU)
 #define CPG_CLKON_14_INITVAL                             (0xFFFFFFFFU)
 #define CPG_CLKON_15_INITVAL                             (0xFFFFFFFFU)
 #define CPG_CLKON_16_INITVAL                             (0x06010601U)
 #define CPG_CLKON_17_INITVAL                             (0x0FFF0FFFU)
 #define CPG_CLKON_18_INITVAL                             (0xFFFCFFFCU)
 #define CPG_CLKON_19_INITVAL                             (0xFFFFFFFFU)
 #define CPG_CLKON_20_INITVAL                             (0xFFFFFFFFU)
 #define CPG_CLKON_21_INITVAL                             (0x000F000FU)

/* Initialize value of TZC setting */
 #define TZC_GATE_KEEPER_CLOSE_FILTER                     (0x00000000U)
 #define TZC_GATE_KEEPER_OPEN_FILTER_0                    (0x00000001U)
 #define TZC_GATE_KEEPER_OPEN_FILTER_0_TO_3               (0x0000000FU)
 #define TZC_REGION_ID_ACCESS_0_FULLACCESS                (0x000F000FU)
 #define TZC_REGION_ATTRIBUTES_0_DISABLE_SECURE_ACCESS    (0x0000000FU)
 #define TZC_SPECULATION_CTRL_DISABLE_SPECUULATION        (0x00000003U)

/* Wait time for clock stabilization */
 #define WAIT_TIME_CLOCK_STABLIZE                         (30U)
 #define WAIT_TIME_POWER_STABLIZE                         (20U)

/*******************************************************************************************************************//**
 *  @brief
 *  @param[IN]   None
 *  @retval      FSP_SUCCESS
 *  @retval      Any Other Error code apart from FSP_SUCCESS is  Unsuccessful open or start
 **********************************************************************************************************************/
fsp_err_t pd_all_on_preproc (void)
{
    fsp_err_t err = FSP_SUCCESS;

    /* Release reset of all CLMAs */
    R_CPG->CPG_CLMA0_CTL  = CPG_CLMA0_CTL_INITVAL;
    R_CPG->CPG_CLMA1_CTL  = CPG_CLMA1_CTL_INITVAL;
    R_CPG->CPG_CLMA2_CTL  = CPG_CLMA2_CTL_INITVAL;
    R_CPG->CPG_CLMA3_CTL  = CPG_CLMA3_CTL_INITVAL;
    R_CPG->CPG_CLMA4_CTL  = CPG_CLMA4_CTL_INITVAL;
    R_CPG->CPG_CLMA5_CTL  = CPG_CLMA5_CTL_INITVAL;
    R_CPG->CPG_CLMA6_CTL  = CPG_CLMA6_CTL_INITVAL;
    R_CPG->CPG_CLMA7_CTL  = CPG_CLMA7_CTL_INITVAL;
    R_CPG->CPG_CLMA8_CTL  = CPG_CLMA8_CTL_INITVAL;
    R_CPG->CPG_CLMA9_CTL  = CPG_CLMA9_CTL_INITVAL;
    R_CPG->CPG_CLMA10_CTL = CPG_CLMA10_CTL_INITVAL;
    R_CPG->CPG_CLMA11_CTL = CPG_CLMA11_CTL_INITVAL;
    R_CPG->CPG_CLMA12_CTL = CPG_CLMA12_CTL_INITVAL;
    R_CPG->CPG_CLMA13_CTL = CPG_CLMA13_CTL_INITVAL;
    R_CPG->CPG_CLMA14_CTL = CPG_CLMA14_CTL_INITVAL;

    return err;
}

/*******************************************************************************************************************//**
 *  @brief
 *  @param[IN]   None
 *  @retval      FSP_SUCCESS
 *  @retval      Any Other Error code apart from FSP_SUCCESS is  Unsuccessful open or start
 **********************************************************************************************************************/
fsp_err_t pd_all_on (void)
{
    fsp_err_t err = FSP_SUCCESS;

    /****** PD_AWO->PD_ALL ******/

    //// Pre-Process
    // #1 Assert the reset of units in the PD_OTHERS, PD_CA55 and PD_DDR.
    R_CPG->CPG_RST_0  = CPG_RST_0_INITVAL;
    R_CPG->CPG_RST_1  = CPG_RST_1_INITVAL;
    R_CPG->CPG_RST_2  = CPG_RST_2_INITVAL;
    R_CPG->CPG_RST_3  = CPG_RST_3_INITVAL;
    R_CPG->CPG_RST_4  = CPG_RST_4_INITVAL;
    R_CPG->CPG_RST_5  = CPG_RST_5_INITVAL;
    R_CPG->CPG_RST_6  = CPG_RST_6_INITVAL;
    R_CPG->CPG_RST_7  = CPG_RST_7_INITVAL;
    R_CPG->CPG_RST_8  = CPG_RST_8_INITVAL;
    R_CPG->CPG_RST_9  = CPG_RST_9_INITVAL;
    R_CPG->CPG_RST_10 = CPG_RST_10_INITVAL;
    R_CPG->CPG_RST_11 = CPG_RST_11_INITVAL;
    R_CPG->CPG_RST_12 = CPG_RST_12_INITVAL;
    R_CPG->CPG_RST_13 = CPG_RST_13_INITVAL;
    R_CPG->CPG_RST_14 = CPG_RST_14_INITVAL;
    R_CPG->CPG_RST_15 = CPG_RST_15_INITVAL;
    R_CPG->CPG_RST_16 = CPG_RST_16_INITVAL;
    R_CPG->CPG_RST_17 = CPG_RST_17_INITVAL;

    // #2 Assert the reset of the CPG circuit in the OTHERS area
    R_CPG->CPG_OTHERS_INI = CPG_OTHERS_INI_RESET;

    // #3 Power on for the PD_OTHERS, PD_CA55 and PD_DDR.
    pmic_sleep_to_active();

    // #4 Waiting for stabilization of power supply for PD_OTHERS, PD_CA55 and PD_DDR.
    R_BSP_SoftwareDelay(WAIT_TIME_CLOCK_STABLIZE, BSP_DELAY_UNITS_MILLISECONDS);

    //// Entry
    // #1 Control the PMU to supply power to the OTHERS area
    R_CPG->CPG_LP_PWC_CTL1 = CPG_LP_PWC_CTL1_OTHER_POWER_ON_START;

    R_BSP_SoftwareDelay(WAIT_TIME_POWER_STABLIZE, BSP_DELAY_UNITS_MILLISECONDS);

    // #2 Check that PWEN1 and PWEN2 are valid
    FSP_HARDWARE_REGISTER_WAIT(((CPG_LP_PWC_CTL2_PWEN_PWEN1_MASK | CPG_LP_PWC_CTL2_PWEN_PWEN2_MASK) &
                                R_CPG->CPG_LP_PWC_CTL2),
                               (CPG_LP_PWC_CTL2_PWEN_PWEN1_HIGH | CPG_LP_PWC_CTL2_PWEN_PWEN2_HIGH));

    // #3 Deassert OTHERS_ON_TRG
    R_CPG->CPG_LP_PWC_CTL1 = CPG_LP_PWC_CTL1_OTHER_POWER_ON_STOP;

    // #4 Check that MSTOP between ACPU bus and MCPU bus is set (1b). If not, set it to 1.
    // Note: After the reset, it is determined that Bit9 (MCPU bus to ACPU bus) is 1
    // and Bit10 (ACPU bus to MCPU bus) is 0.
    // Therefore, the register value check is omitted and only set 1 to Bit10.
    R_CPG->CPG_BUS_12_MSTOP = CPG_BUS_12_MSTOP_INITVAL;

    // #5 Deassert the reset of the CPG circuit in the OTHERS area
    R_CPG->CPG_OTHERS_INI = CPG_OTHERS_INI_RELEASE_RESET;

    // #6, #7 PLL startup
    pll_init_cm33boot();

    // #8 Supply clock for units in the PD_OTHERS area / PD_CA55 area
    R_CPG->CPG_CLKON_0  = CPG_CLKON_0_INITVAL;
    R_CPG->CPG_CLKON_1  = CPG_CLKON_1_INITVAL;
    R_CPG->CPG_CLKON_2  = CPG_CLKON_2_INITVAL;
    R_CPG->CPG_CLKON_3  = CPG_CLKON_3_INITVAL;
    R_CPG->CPG_CLKON_4  = CPG_CLKON_4_INITVAL;
    R_CPG->CPG_CLKON_5  = CPG_CLKON_5_INITVAL;
    R_CPG->CPG_CLKON_6  = CPG_CLKON_6_INITVAL;
    R_CPG->CPG_CLKON_7  = CPG_CLKON_7_INITVAL;
    R_CPG->CPG_CLKON_8  = CPG_CLKON_8_INITVAL;
    R_CPG->CPG_CLKON_9  = CPG_CLKON_9_INITVAL;
    R_CPG->CPG_CLKON_10 = CPG_CLKON_10_INITVAL;
    R_CPG->CPG_CLKON_11 = CPG_CLKON_11_INITVAL;
    R_CPG->CPG_CLKON_12 = CPG_CLKON_12_INITVAL;
    R_CPG->CPG_CLKON_13 = CPG_CLKON_13_INITVAL;
    R_CPG->CPG_CLKON_14 = CPG_CLKON_14_INITVAL;
    R_CPG->CPG_CLKON_15 = CPG_CLKON_15_INITVAL;
    R_CPG->CPG_CLKON_16 = CPG_CLKON_16_INITVAL;
    R_CPG->CPG_CLKON_17 = CPG_CLKON_17_INITVAL;
    R_CPG->CPG_CLKON_18 = CPG_CLKON_18_INITVAL;
    R_CPG->CPG_CLKON_19 = CPG_CLKON_19_INITVAL;
    R_CPG->CPG_CLKON_20 = CPG_CLKON_20_INITVAL;
    R_CPG->CPG_CLKON_21 = CPG_CLKON_21_INITVAL;

    // #9,#10 Request the PMU to set PD_OTHERS to ON, Request the PMU to control the power supply domain
    R_CPG->CPG_LP_PMU_CTL1 = (CPG_LP_PMU_CTL1_DOMAIN_CTRL_REQ_OUTPUT | CPG_LP_PMU_CTL1_DOMAIN_ON_REQ);

    // #11 Check (polling) the completion of power domain control and the state (ON state) of PD_OTHERS
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_LP_PMU_CTL1_PD_OTHERS_ACK_Msk | R_CPG_CPG_LP_PMU_CTL1_CTRLACK_Msk) &
                                R_CPG->CPG_LP_PMU_CTL1),
                               CPG_LP_PMU_CTL1_DOMAIN_ON_COMPLETE);

    // #12 Clear the request for control of the power domain
    R_CPG->CPG_LP_PMU_CTL1 = CPG_LP_PMU_CTL1_DOMAIN_ON_REQ;

    // #13 Check (polling) the status of the completion flag for SRAM rescue information transfer
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_OTP_HANDSHAKE_MON_DFT_DONE_Msk & R_CPG->CPG_OTP_HANDSHAKE_MON),
                               CPG_OTP_HANDSHAKE_MON_COMPLETE);

    return err;
}

/*******************************************************************************************************************//**
 *  @brief
 *  @param[IN]   None
 *  @retval      FSP_SUCCESS
 *  @retval      Any Other Error code apart from FSP_SUCCESS is  Unsuccessful open or start
 **********************************************************************************************************************/
fsp_err_t pd_all_on_postproc (void)
{
    fsp_err_t err = FSP_SUCCESS;

    /* Allow access to RCPU-Bus(Initialize TZC400-RCPU) */
    R_TZC_AXI_RCPU->GATE_KEEPER        = TZC_GATE_KEEPER_CLOSE_FILTER;      /* Close filter before initialization */
    R_TZC_AXI_RCPU->REGION_ID_ACCESS_0 = TZC_REGION_ID_ACCESS_0_FULLACCESS; /* Permit Secure/Nonsecure access */
    R_TZC_AXI_RCPU->GATE_KEEPER        = TZC_GATE_KEEPER_OPEN_FILTER_0;     /* Open filter #0 */

    /* Allow access to CR8(TCM) */
    R_CPG->CPG_BUS_10_MSTOP = CPG_BUS_10_MSTOP_INITVAL;

    /* Allow access to ACPU SRAM */
    R_TZC_SRAMA->GATE_KEEPER        = TZC_GATE_KEEPER_CLOSE_FILTER;      /* Close filter before initialization */
    R_TZC_SRAMA->REGION_ID_ACCESS_0 = TZC_REGION_ID_ACCESS_0_FULLACCESS; /* Permit Secure/Nonsecure access */
    R_TZC_SRAMA->GATE_KEEPER        = TZC_GATE_KEEPER_OPEN_FILTER_0;     /* Open filter #0 */

    /* Release Reset of GIC and ACPU SRAMs */
    R_CPG->CPG_RST_3 = CPG_RST_3_RELEASE_RESETVAL;
    R_CPG->CPG_RST_4 = CPG_RST_4_RELEASE_RESETVAL;

    /* Allow access to xSPI(Initialize TZC400_XSPI) */
    R_TZC_XSPI->GATE_KEEPER         = TZC_GATE_KEEPER_CLOSE_FILTER;                  /* Close filter before initialization */
    R_TZC_XSPI->REGION_ID_ACCESS_0  = TZC_REGION_ID_ACCESS_0_FULLACCESS;             /* Permit Secure/Nonsecure access */
    R_TZC_XSPI->REGION_ATTRIBUTES_0 = TZC_REGION_ATTRIBUTES_0_DISABLE_SECURE_ACCESS; /* Disable secure read/write access */
    R_TZC_XSPI->SPECULATION_CTRL    = TZC_SPECULATION_CTRL_DISABLE_SPECUULATION;     /* Disable read/write speculation */
    R_TZC_XSPI->GATE_KEEPER         = TZC_GATE_KEEPER_OPEN_FILTER_0_TO_3;            /* Open filter #0-#3 */

    return err;
}

#endif                                 /*defined(BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT) && (BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT == 1)*/

/*******************************************************************************************************************//**
 * @} (end addtogroup pd_all_on)
 **********************************************************************************************************************/
