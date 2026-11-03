/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include "xspi_init.h"

/* Command of Flash memory Definitions */
#define CMD_WRITE_ENHANCE_VOLATILE_CFG_REG             (0x61)
#define DATA_DEFAULT_WRITE_ENHANCE_VOLATILE_CFG_REG    (0xFF)
#define DATA_DUAL_IO_ENHANCE_VOLATILE_CFG_REG          (0xBF)
#define DATA_QUAD_IO_ENHANCE_VOLATILE_CFG_REG          (0x7F)
#define LENGTH_CMD_WRITE_ENHANCE_VOLATILE_CFG_REG      (0x01)
#define LENGTH_DATA_WRITE_ENHANCE_VOLATILE_CFG_REG     (0x01)
#define CMD_WRITE_ENABLE_REG                           (0x06)
#define LENGTH_CMD_WRITE_ENABLE_REG                    (0x01)

/* CPG_SSEL1 register Definitions */
#define CPG_SSEL1_SELCTL3_SMUX2_XSPI_CLK0              (0U)
#define CPG_SSEL1_SELCTL3_CDIV5_CLK320_PLLCM33_FIX     (1U)
#define CPG_SSEL1_SELCTL2_CDIV3_CLK533_PLLCM33_FIX     (0U)
#define CPG_SSEL1_SELCTL2_CDIV4_CLK400_PLLCM33_FIX     (1U)

/* CPG_CSDIV0 register Definitions */
#define CPG_CSDIV0_DIVCTL3_DIV_1_2                     (0U)
#define CPG_CSDIV0_DIVCTL3_DIV_1_4                     (1U)
#define CPG_CSDIV0_DIVCTL3_DIV_1_8                     (2U)
#define CPG_CSDIV0_DIVCTL3_DIV_1_16                    (3U)

/* Dummy read address on Flash memory */
#define DUMMY_READ_ADDR_FLASH                          (0x60000000U)

/* Parameter for "WRITE ENHANCED VOLATILE CONFIGURATION REGISTER" command. */
static spi_flash_direct_transfer_t g_qspi0_w =
{
    .address        = 0,
    .data           = DATA_DEFAULT_WRITE_ENHANCE_VOLATILE_CFG_REG,
    .command        = CMD_WRITE_ENHANCE_VOLATILE_CFG_REG,
    .dummy_cycles   = SPI_FLASH_DUMMY_CLOCKS_0,
    .command_length = LENGTH_CMD_WRITE_ENHANCE_VOLATILE_CFG_REG,
    .address_length = 0,
    .data_length    = LENGTH_DATA_WRITE_ENHANCE_VOLATILE_CFG_REG,
};

/* Parameter for "WRITE ENABLE REGISTER" command. */
static spi_flash_direct_transfer_t g_qspi0_we =
{
    .address        = 0,
    .data           = 0,
    .command        = CMD_WRITE_ENABLE_REG,
    .dummy_cycles   = SPI_FLASH_DUMMY_CLOCKS_0,
    .command_length = LENGTH_CMD_WRITE_ENABLE_REG,
    .address_length = 0,
    .data_length    = 0,
};

/*******************************************************************************************************************//**
 * @brief  Open r_xspi_qspi driver
 *
 **********************************************************************************************************************/
void xspi_open (void)
{
    /* Set xSPI clock: The frequency is set to 50MHz to issue the H'03(READ) command. */
    uint32_t reg = 0;
    reg             |= R_CPG_CPG_SSEL1_SELCTL3WEN_Msk | R_CPG_CPG_SSEL1_SELCTL2WEN_Msk;           // write enable
    reg             |= CPG_SSEL1_SELCTL3_SMUX2_XSPI_CLK0 << R_CPG_CPG_SSEL1_SELCTL3_Pos;          // SMUX2_XSPI_CLK1: 0b= SMUX2_XSPI_CLK0
    reg             |= CPG_SSEL1_SELCTL2_CDIV4_CLK400_PLLCM33_FIX << R_CPG_CPG_SSEL1_SELCTL2_Pos; // SMUX2_XSPI_CLK0: 1b= CDIV4_CLK400_PLLCM33_FIX
    R_CPG->CPG_SSEL1 = reg;

    /* Divisor=1/4 */
    reg               = 0;
    reg              |= R_CPG_CPG_CSDIV0_DIVCTL3WEN_Msk;                            // write enable
    reg              |= CPG_CSDIV0_DIVCTL3_DIV_1_4 << R_CPG_CPG_CSDIV0_DIVCTL3_Pos; // CSDIV_2to16_PLLCM33_XSPI: 01b= 1/4
    R_CPG->CPG_CSDIV0 = reg;

    /* Set PFC_OEN register to xSPI enable */
    R_BSP_XSPIOutputEnableCfg();

    /* Open xSPI driver */
    g_qspi0.p_api->open(g_qspi0.p_ctrl, g_qspi0.p_cfg);
}

/*******************************************************************************************************************//**
 * @brief  Pre-initialize function for r_xspi_qspi driver
 *
 * Specify this function to "Extra->Pre initialize function" of the SmartCconfigurator property of the r_xspi_qspi driver.
 *
 **********************************************************************************************************************/
fsp_err_t xspi_pre_init (spi_flash_api_t const * p_api, xspi_qspi_instance_ctrl_t * p_ctrl)
{
    FSP_PARAMETER_NOT_USED(p_api);

    /* Reset the device connected to CS0 */
    p_ctrl->p_reg->LIOCTL_b.RSTCS0 = 0;
    R_BSP_SoftwareDelay(1, BSP_DELAY_UNITS_MICROSECONDS);
    p_ctrl->p_reg->LIOCTL_b.RSTCS0 = 1;

    /* Set the operating mode on the device side */
    if ((SPI_FLASH_PROTOCOL_2S_2S_2S == p_ctrl->p_cfg->spi_protocol) ||
        (SPI_FLASH_PROTOCOL_4S_4S_4S == p_ctrl->p_cfg->spi_protocol))
    {
        if (SPI_FLASH_PROTOCOL_2S_2S_2S == p_ctrl->p_cfg->spi_protocol)
        {
            g_qspi0_w.data = DATA_DUAL_IO_ENHANCE_VOLATILE_CFG_REG; /* Dual I/O protocol(bit6) Enable */
        }
        else
        {
            g_qspi0_w.data = DATA_QUAD_IO_ENHANCE_VOLATILE_CFG_REG; /* Quad I/O protocol(bit5) Enable */
        }

        /* Set SPI protocol to 1S-1S-1S */
        p_api->spiProtocolSet(p_ctrl, SPI_FLASH_PROTOCOL_1S_1S_1S);

        /* Issuing the WREN command */
        p_api->directTransfer(p_ctrl, &g_qspi0_we, SPI_FLASH_DIRECT_TRANSFER_DIR_WRITE);

        /* Issuing the Write enhanced volatile configuraiton register command */
        p_api->directTransfer(p_ctrl, &g_qspi0_w, SPI_FLASH_DIRECT_TRANSFER_DIR_WRITE);

        /* Set SPI protocol to spi_protocol */
        p_api->spiProtocolSet(p_ctrl, g_qspi0_cfg.spi_protocol);
    }

    return FSP_SUCCESS;
}

/*******************************************************************************************************************//**
 * @brief  Post-initialize function for r_xspi_qspi driver
 *
 * Specify this function to "Extra->Post initialize function" of the SmartCconfigurator property of the r_xspi_qspi driver.
 *
 **********************************************************************************************************************/
fsp_err_t xspi_post_init (spi_flash_api_t const * p_api, xspi_qspi_instance_ctrl_t * p_ctrl)
{
    FSP_PARAMETER_NOT_USED(p_api);
    FSP_PARAMETER_NOT_USED(p_ctrl);

    return FSP_SUCCESS;
}

void xspi_close (void) {
    xspi_qspi_instance_ctrl_t * p_instance_ctrl = (xspi_qspi_instance_ctrl_t *) g_qspi0.p_ctrl;

    /*Issue dummy read (4Byte INCR) for both channel Accept response of dummy read*/
    FSP_REGISTER_READ(*((uint32_t *) DUMMY_READ_ADDR_FLASH));

    p_instance_ctrl->p_reg->BMCTL0 = 0x0;

    g_qspi0.p_api->close(g_qspi0.p_ctrl);

#ifdef BSP_CFG_MCU_LAUNCH_CA55
    uint32_t reg = 1;
    reg             |= R_CPG_CPG_SSEL1_SELCTL3WEN_Msk | R_CPG_CPG_SSEL1_SELCTL2WEN_Msk;           // write enable
    reg             |= CPG_SSEL1_SELCTL3_CDIV5_CLK320_PLLCM33_FIX << R_CPG_CPG_SSEL1_SELCTL3_Pos; // SMUX2_XSPI_CLK1: 1b= CDIV5_CLK320_PLLCM33_FIX
    reg             |= CPG_SSEL1_SELCTL2_CDIV3_CLK533_PLLCM33_FIX << R_CPG_CPG_SSEL1_SELCTL2_Pos; // SMUX2_XSPI_CLK0: 0b= : CDIV3_CLK533_PLLCM33_FIX (default)
    R_CPG->CPG_SSEL1 = reg;

    /* Divisor=1/8 */
    reg               = 0;
    reg              |= R_CPG_CPG_CSDIV0_DIVCTL3WEN_Msk;                            // write enable
    reg              |= CPG_CSDIV0_DIVCTL3_DIV_1_8 << R_CPG_CPG_CSDIV0_DIVCTL3_Pos; // CSDIV_2to16_PLLCM33_XSPI: 10b= 1/8
    R_CPG->CPG_CSDIV0 = reg;
#endif
    R_BSP_MODULE_RSTON(FSP_IP_XSPI, 0);
}
