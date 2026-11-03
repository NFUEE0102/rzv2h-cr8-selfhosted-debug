/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include "pll_init.h"

/*******************************************************************************************************************//**
 * @brief Initialize the PLLs associated with the clocks required for PD_ALL_ON operation. (For CM33 coldboot)
 *
 *  @param[IN]   None
 *  @retval      None
 **********************************************************************************************************************/
void pll_init_cm33boot (void)
{
#if defined(BSP_CFG_CLOCK_PLLCLNCLK_HZ)

    /*****************************************/
    /* Setting PLLCLN                        */
    /*****************************************/

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLCLN_STBY = R_CPG_CPG_PLLCLN_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLCLN_STBY_RESETB_Msk;

    /* Wait until the PLL is in locked-state */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_PLLCLN_MON_PLLn_LOCK_Msk & R_CPG->CPG_PLLCLN_MON),
                               R_CPG_CPG_PLLCLN_MON_PLLn_LOCK_Msk);
#endif

#if defined(BSP_CFG_CLOCK_PLLDTYCLK_HZ)

    /*****************************************/
    /* Setting PLLDTY                        */
    /*****************************************/

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLDTY_STBY = R_CPG_CPG_PLLDTY_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLDTY_STBY_RESETB_Msk;

    /* Wait until the PLL is in locked-state */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_PLLDTY_MON_PLLn_LOCK_Msk & R_CPG->CPG_PLLDTY_MON),
                               R_CPG_CPG_PLLDTY_MON_PLLn_LOCK_Msk);
#endif

#if defined(BSP_CFG_CLOCK_PLLCA55CLK_HZ)

    /*****************************************/
    /* Setting PLLCA55                       */
    /*****************************************/

#if BSP_CFG_MCU_CA55_CLOCK_UP
    /* Output clock settings 1 */
    R_CPG->CPG_PLLCA55_CLK1 = CPG_PLLCA55_CLK1_1_8GHZ;

    /* Setting the output clock and SSC modulation value 2 */
    R_CPG->CPG_PLLCA55_CLK2 = CPG_PLLCA55_CLK2_1_8GHZ;
#else
    /* Output clock settings 1 */
    R_CPG->CPG_PLLCA55_CLK1 = CPG_PLLCA55_CLK1_1_7GHZ;

    /* Setting the output clock and SSC modulation value 2 */
    R_CPG->CPG_PLLCA55_CLK2 = CPG_PLLCA55_CLK2_1_7GHZ;
#endif

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLCA55_STBY = R_CPG_CPG_PLLCA55_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLCA55_STBY_RESETB_Msk;

    /* Wait until the PLL is in locked-state */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_PLLCA55_MON_PLLn_LOCK_Msk & R_CPG->CPG_PLLCA55_MON),
                               R_CPG_CPG_PLLCA55_MON_PLLn_LOCK_Msk);
#endif

#if defined(BSP_CFG_CLOCK_PLLVDOCLK_HZ)

    /*****************************************/
    /* Setting PLLVDO                        */
    /*****************************************/

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLVDO_STBY = R_CPG_CPG_PLLVDO_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLVDO_STBY_RESETB_Msk;

    /* Wait until the PLL is in locked-state */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_PLLVDO_MON_PLLn_LOCK_Msk & R_CPG->CPG_PLLVDO_MON),
                               R_CPG_CPG_PLLVDO_MON_PLLn_LOCK_Msk);
#endif

#if defined(BSP_CFG_CLOCK_PLLDRPCLK_HZ)

    /*****************************************/
    /* Setting PLLDRP                        */
    /*****************************************/

    /* Output clock settings 1 */
    R_CPG->CPG_PLLDRP_CLK1 = CPG_PLLDRP_CLK1_INITVAL;

    /* Setting the output clock and SSC modulation value 2 */
    R_CPG->CPG_PLLDRP_CLK2 = CPG_PLLDRP_CLK2_INITVAL;

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLDRP_STBY = R_CPG_CPG_PLLDRP_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLDRP_STBY_RESETB_Msk;

    /* Wait until the PLL is in locked-state */
    FSP_HARDWARE_REGISTER_WAIT((R_CPG_CPG_PLLDRP_MON_PLLn_LOCK_Msk & R_CPG->CPG_PLLDRP_MON),
                               R_CPG_CPG_PLLDRP_MON_PLLn_LOCK_Msk);
#endif
}

/*******************************************************************************************************************//**
 * @brief Initialize optional PLLs that are not involved in boot operation.
 *
 *  @param[IN]   None
 *  @retval      None
 **********************************************************************************************************************/
void pll_init_other (void)
{
#if defined(BSP_CFG_CLOCK_PLLETHCLK_HZ)

    /*****************************************/
    /* Setting PLLETH                        */
    /*****************************************/

    /* Wait until the PLL is in standby mode and unlocked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLETH_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLETH_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLETH_MON),
                               0);

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLETH_STBY = R_CPG_CPG_PLLETH_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLETH_STBY_RESETB_Msk;

    /* Wait until the PLL is in normal mode and locked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLETH_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLETH_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLETH_MON),
                               (R_CPG_CPG_PLLETH_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLETH_MON_PLLn_RESETB_Msk));
#endif

#if defined(BSP_CFG_CLOCK_PLLDSICLK_HZ)

    /*****************************************/
    /* Setting PLLDSI                        */
    /*****************************************/

    /* Wait until the PLL is in standby mode and unlocked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLDSI_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDSI_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLDSI_MON),
                               0);

    /* Output clock settings 1 */
    R_CPG->CPG_PLLDSI_CLK1 = CPG_PLLDSI_CLK1_INITVAL;

    /* Setting the output clock and SSC modulation value 2 */
    R_CPG->CPG_PLLDSI_CLK2 = CPG_PLLDSI_CLK2_INITVAL;

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLDSI_STBY = R_CPG_CPG_PLLDSI_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLDSI_STBY_RESETB_Msk;

    /* Wait until the PLL is in normal mode and locked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLDSI_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDSI_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLDSI_MON),
                               (R_CPG_CPG_PLLDSI_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDSI_MON_PLLn_RESETB_Msk));
#endif

#if defined(BSP_CFG_CLOCK_PLLDDR0CLK_HZ)

    /*****************************************/
    /* Setting PLLDDR0                       */
    /*****************************************/

    /* Wait until the PLL is in standby mode and unlocked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLDDR0_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDDR0_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLDDR0_MON),
                               0);

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLDDR0_STBY = R_CPG_CPG_PLLDDR0_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLDDR0_STBY_RESETB_Msk;

    /* Wait until the PLL is in normal mode and locked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLDDR0_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDDR0_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLDDR0_MON),
                               (R_CPG_CPG_PLLDDR0_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDDR0_MON_PLLn_RESETB_Msk));
#endif

#if defined(BSP_CFG_CLOCK_PLLDDR1CLK_HZ)

    /*****************************************/
    /* Setting PLLDDR1                       */
    /*****************************************/

    /* Wait until the PLL is in standby mode and unlocked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLDDR1_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDDR1_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLDDR1_MON),
                               0);

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLDDR1_STBY = R_CPG_CPG_PLLDDR1_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLDDR1_STBY_RESETB_Msk;

    /* Wait until the PLL is in normal mode and locked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLDDR1_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDDR1_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLDDR1_MON),
                               (R_CPG_CPG_PLLDDR1_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLDDR1_MON_PLLn_RESETB_Msk));
#endif

#if defined(BSP_CFG_CLOCK_PLLGPUCLK_HZ)

    /*****************************************/
    /* Setting PLLGPU                        */
    /*****************************************/

    /* Wait until the PLL is in standby mode and unlocked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLGPU_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLGPU_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLGPU_MON),
                               0);

    /* Output clock settings 1 */
    R_CPG->CPG_PLLGPU_CLK1 = CPG_PLLGPU_CLK1_INITVAL;

    /* Setting the output clock and SSC modulation value 2 */
    R_CPG->CPG_PLLGPU_CLK2 = CPG_PLLGPU_CLK2_INITVAL;

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLGPU_STBY = R_CPG_CPG_PLLGPU_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLGPU_STBY_RESETB_Msk;

    /* Wait until the PLL is in normal mode and locked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLGPU_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLGPU_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLGPU_MON),
                               (R_CPG_CPG_PLLGPU_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLGPU_MON_PLLn_RESETB_Msk));
#endif
}

/*******************************************************************************************************************//**
 * @brief Stop the CA55's PLL and then restart it at 1.8GHz (For CA55 coldboot)
 *
 *  @param[IN]   None
 *  @retval      None
 **********************************************************************************************************************/
void pll_reboot_ca55_at_1_8GHz (void)
{
    /*****************************************/
    /* Setting PLLCA55                       */
    /*****************************************/
    /* Setting PLL for standby mode */
    R_CPG->CPG_PLLCA55_STBY = R_CPG_CPG_PLLCA55_STBY_RESETB_WEN_Msk ;

    /* Wait until the PLL is in standby */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLCA55_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLVDO_STBY_RESETB_Msk) &
                                R_CPG->CPG_PLLCA55_MON),
                               0);

    /* Output clock settings 1 */
    R_CPG->CPG_PLLCA55_CLK1 = CPG_PLLCA55_CLK1_1_8GHZ;

    /* Setting the output clock and SSC modulation value 2 */
    R_CPG->CPG_PLLCA55_CLK2 = CPG_PLLCA55_CLK2_1_8GHZ;

    /* Setting PLL for normal mode */
    R_CPG->CPG_PLLCA55_STBY = R_CPG_CPG_PLLCA55_STBY_RESETB_WEN_Msk | R_CPG_CPG_PLLCA55_STBY_RESETB_Msk;

    /* Wait until the PLL is in locked-state */
    FSP_HARDWARE_REGISTER_WAIT(((R_CPG_CPG_PLLCA55_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLCA55_MON_PLLn_RESETB_Msk) &
                                R_CPG->CPG_PLLCA55_MON),
                               (R_CPG_CPG_PLLCA55_MON_PLLn_LOCK_Msk | R_CPG_CPG_PLLCA55_MON_PLLn_RESETB_Msk));
}
