/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include "i2c_pmic.h"
#if BSP_CFG_RTOS == 2
 #include "FreeRTOS.h"
 #include "FreeRTOSConfig.h"
 #include "task.h"
#endif

/*******************************************************************************************************************//**
 * @addtogroup r_riic_master_pmic
 * @{
 **********************************************************************************************************************/

#if defined(BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT) && (BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT == 1)

/*
 * Global Variables
 */

/* Reading I2C call back event through i2c_Master callback */
static volatile i2c_master_event_t i2c_event = I2C_MASTER_EVENT_ABORTED;

/*
 * private function declarations
 */
static fsp_err_t pmic_read_reg(uint8_t reg_address, uint8_t * reg_data);
static fsp_err_t pmic_write_reg(uint8_t reg_address, uint8_t reg_data);
static fsp_err_t validate_i2c_event(void);

/* PMIC Register Address Definitions */
 #define RAA215300_REG_BUCK1_ENABLE_ADDR                                              (0x20)
 #define RAA215300_REG_BUCK1_ACTIVE_ADDR                                              (0x21)
 #define RAA215300_REG_BUCK1_SLEEP_ADDR                                               (0x22)
 #define RAA215300_REG_BUCK1_POWER_ON_ADDR                                            (0x23)
 #define RAA215300_REG_BUCK1_POWER_OFF_ADDR                                           (0x24)
 #define RAA215300_REG_BUCK1_SR_ADDR                                                  (0x25)
 #define RAA215300_REG_BUCK1_CONFIG_ADDR                                              (0x26)
 #define RAA215300_REG_BUCK2_ENABLE_ADDR                                              (0x27)
 #define RAA215300_REG_BUCK2_ACTIVE_ADDR                                              (0x28)
 #define RAA215300_REG_BUCK2_SLEEP_ADDR                                               (0x29)
 #define RAA215300_REG_BUCK2_POWER_ON_ADDR                                            (0x2A)
 #define RAA215300_REG_BUCK2_POWER_OFF_ADDR                                           (0x2B)
 #define RAA215300_REG_BUCK2_SR_ADDR                                                  (0x2C)
 #define RAA215300_REG_BUCK2_CONFIG_ADDR                                              (0x2D)
 #define RAA215300_REG_BUCK3_ENABLE_ADDR                                              (0x2E)
 #define RAA215300_REG_BUCK3_ACTIVE_ADDR                                              (0x2F)
 #define RAA215300_REG_BUCK3_SLEEP_ADDR                                               (0x30)
 #define RAA215300_REG_BUCK3_POWER_ON_ADDR                                            (0x31)
 #define RAA215300_REG_BUCK3_POWER_OFF_ADDR                                           (0x32)
 #define RAA215300_REG_BUCK3_SR_ADDR                                                  (0x33)
 #define RAA215300_REG_BUCK3_CONFIG_ADDR                                              (0x34)
 #define RAA215300_REG_BUCK4_ENABLE_ADDR                                              (0x35)
 #define RAA215300_REG_BUCK4_ACTIVE_ADDR                                              (0x36)
 #define RAA215300_REG_BUCK4_SLEEP_ADDR                                               (0x37)
 #define RAA215300_REG_BUCK4_POWER_ON_ADDR                                            (0x38)
 #define RAA215300_REG_BUCK4_POWER_OFF_ADDR                                           (0x39)
 #define RAA215300_REG_BUCK4_SR_ADDR                                                  (0x3A)
 #define RAA215300_REG_BUCK4_CONFIG_ADDR                                              (0x3B)
 #define RAA215300_REG_BUCK5_ENABLE_ADDR                                              (0x3C)
 #define RAA215300_REG_BUCK5_ACTIVE_ADDR                                              (0x3D)
 #define RAA215300_REG_BUCK5_SLEEP_ADDR                                               (0x3E)
 #define RAA215300_REG_BUCK5_POWER_ON_ADDR                                            (0x3F)
 #define RAA215300_REG_BUCK5_POWER_OFF_ADDR                                           (0x40)
 #define RAA215300_REG_BUCK5_SR_ADDR                                                  (0x41)
 #define RAA215300_REG_BUCK5_CONFIG_ADDR                                              (0x42)
 #define RAA215300_REG_BUCK6_ENABLE_ADDR                                              (0x43)
 #define RAA215300_REG_BUCK6_ACTIVE_ADDR                                              (0x44)
 #define RAA215300_REG_BUCK6_SLEEP_ADDR                                               (0x45)
 #define RAA215300_REG_BUCK6_POWER_ON_ADDR                                            (0x46)
 #define RAA215300_REG_BUCK6_POWER_OFF_ADDR                                           (0x47)
 #define RAA215300_REG_BUCK6_SR_ADDR                                                  (0x48)
 #define RAA215300_REG_BUCK6_CONFIG_ADDR                                              (0x49)
 #define RAA215300_REG_LDO1_ACTIVE_ADDR                                               (0x4A)
 #define RAA215300_REG_LDO1_SLEEP_ADDR                                                (0x4B)
 #define RAA215300_REG_LDO1_POWER_ON_ADDR                                             (0x4C)
 #define RAA215300_REG_LDO1_POWER_OFF_ADDR                                            (0x4D)
 #define RAA215300_REG_LDO1_SR_ADDR                                                   (0x4E)
 #define RAA215300_REG_LDO2_ACTIVE_ADDR                                               (0x4F)
 #define RAA215300_REG_LDO2_SLEEP_ADDR                                                (0x50)
 #define RAA215300_REG_LDO2_POWER_ON_ADDR                                             (0x51)
 #define RAA215300_REG_LDO2_POWER_OFF_ADDR                                            (0x52)
 #define RAA215300_REG_LDO2_SR_ADDR                                                   (0x53)
 #define RAA215300_REG_LDO3_ACTIVE_SLEEP_ADDR                                         (0x54)
 #define RAA215300_REG_LDO3_POWER_ON_ADDR                                             (0x55)
 #define RAA215300_REG_LDO3_POWER_OFF_ADDR                                            (0x56)
 #define RAA215300_REG_LDO3_SR_ADDR                                                   (0x57)
 #define RAA215300_REG_LDOS_CONFIG_ADDR                                               (0x58)
 #define RAA215300_REG_FAULT_LATCHED_STATUS1_ADDR                                     (0x59)
 #define RAA215300_REG_FAULT_LATCHED_STATUS2_ADDR                                     (0x5A)
 #define RAA215300_REG_FAULT_LATCHED_STATUS3_ADDR                                     (0x5B)
 #define RAA215300_REG_FAULT_LATCHED_STATUS4_ADDR                                     (0x5C)
 #define RAA215300_REG_FAULT_LATCHED_STATUS5_ADDR                                     (0x5D)
 #define RAA215300_REG_FAULT_LATCHED_STATUS6_ADDR                                     (0x5E)
 #define RAA215300_REG_FAULT_LIVE_STATUS1_ADDR                                        (0x5F)
 #define RAA215300_REG_FAULT_LIVE_STATUS2_ADDR                                        (0x60)
 #define RAA215300_REG_FAULT_LIVE_STATUS3_ADDR                                        (0x61)
 #define RAA215300_REG_FAULT_LIVE_STATUS4_ADDR                                        (0x62)
 #define RAA215300_REG_FAULT_LIVE_STATUS6_ADDR                                        (0x63)
 #define RAA215300_REG_NINT_MASK1_ADDR                                                (0x64)
 #define RAA215300_REG_NINT_MASK2_ADDR                                                (0x65)
 #define RAA215300_REG_NINT_MASK3_ADDR                                                (0x66)
 #define RAA215300_REG_NINT_MASK4_ADDR                                                (0x67)
 #define RAA215300_REG_NINT_MASK6_ADDR                                                (0x68)
 #define RAA215300_REG_FAULT_CONFIG1_ADDR                                             (0x69)
 #define RAA215300_REG_FAULT_CONFIG2_ADDR                                             (0x6A)
 #define RAA215300_REG_FAULT_CONFIG3_ADDR                                             (0x6B)
 #define RAA215300_REG_BLOCK_EN_ADDR                                                  (0x6C)
 #define RAA215300_REG_SOFTWARE_RESET_ADDR                                            (0x6D)
 #define RAA215300_REG_I2C_TRIGGER_POWER_OFF_ADDR                                     (0x6E)
 #define RAA215300_REG_CONFIG1_ADDR                                                   (0x6F)
 #define RAA215300_REG_CONFIG2_ADDR                                                   (0x70)
 #define RAA215300_REG_CONFIG3_ADDR                                                   (0x71)
 #define RAA215300_REG_MPIO0_POWER_ON_ADDR                                            (0x72)
 #define RAA215300_REG_MPIO0_POWER_OFF_ADDR                                           (0x73)
 #define RAA215300_REG_MPIO1_POWER_ON_ADDR                                            (0x74)
 #define RAA215300_REG_MPIO1_POWER_OFF_ADDR                                           (0x75)
 #define RAA215300_REG_MPIO2_POWER_ON_ADDR                                            (0x76)
 #define RAA215300_REG_MPIO2_POWER_OFF_ADDR                                           (0x77)
 #define RAA215300_REG_MPIO3_POWER_ON_ADDR                                            (0x78)
 #define RAA215300_REG_MPIO3_POWER_OFF_ADDR                                           (0x79)
 #define RAA215300_REG_MPIO4_POWER_ON_ADDR                                            (0x7A)
 #define RAA215300_REG_MPIO4_POWER_OFF_ADDR                                           (0x7B)
 #define RAA215300_REG_MPIO5_POWER_ON_ADDR                                            (0x7C)
 #define RAA215300_REG_MPIO5_POWER_OFF_ADDR                                           (0x7D)
 #define RAA215300_REG_MPIO0_INPUT_STATUS_ADDR                                        (0x7E)
 #define RAA215300_REG_MPIO0_I2C_OUTPUT_ADDR                                          (0x7F)
 #define RAA215300_REG_MPIO0_ASSERTION_ADDR                                           (0x80)
 #define RAA215300_REG_INPUT_PIN_STATUS_ADDR                                          (0x81)
 #define RAA215300_REG_REPORT_BUCK_MODE_ADDR                                          (0x82)
 #define RAA215300_REG_ECC_DETAIL1_ADDR                                               (0x83)
 #define RAA215300_REG_ECC_DETAIL2_ADDR                                               (0x84)
 #define RAA215300_REG_EE_DETAIL_ADDR                                                 (0x85)
 #define RAA215300_REG_SPREAD_SPECTRUM1_ADDR                                          (0x86)
 #define RAA215300_REG_SPREAD_SPECTRUM2_ADDR                                          (0x87)
 #define RAA215300_REG_SPREAD_SPECTRUM3_ADDR                                          (0x88)
 #define RAA215300_REG_SHUTDOWN_CONFIG_ADDR                                           (0x89)
 #define RAA215300_REG_MPIO0_CONFIG_ADDR                                              (0x8A)
 #define RAA215300_REG_MPIO1_CONFIG_ADDR                                              (0x8B)
 #define RAA215300_REG_MPIO2_CONFIG_ADDR                                              (0x8C)
 #define RAA215300_REG_MPIO3_CONFIG_ADDR                                              (0x8D)
 #define RAA215300_REG_MPIO4_CONFIG_ADDR                                              (0x8E)
 #define RAA215300_REG_MPIO5_CONFIG_ADDR                                              (0x8F)

 #define RAA215300_REG_HW_REV_ADDR                                                    (0xF8)
 #define RAA215300_REG_EEPROM_CONTROL_ADDR                                            (0xFF)

/* PMIC Register Data Definitions */
 #define RAA215300_REG_BUCK1_ENABLE_DATA_ABS                                          (0x04)
 #define RAA215300_REG_BUCK1_ENABLE_DATA_ABS_ACTIVE                                   (0x05)

 #define RAA215300_REG_BUCK3_ENABLE_DATA_ABS                                          (0x04)
 #define RAA215300_REG_BUCK3_ENABLE_DATA_ABS_ACTIVE                                   (0x05)

 #define RAA215300_REG_BUCK4_ENABLE_DATA_ABS_SLEEP                                    (0x06)
 #define RAA215300_REG_BUCK4_ENABLE_DATA_ABS_SLEEP_ACTIVE                             (0x07)

 #define RAA215300_REG_BUCK5_ENABLE_DATA_ABS_SLEEP                                    (0x06)
 #define RAA215300_REG_BUCK5_ENABLE_DATA_ABS_SLEEP_ACTIVE                             (0x07)

 #define RAA215300_REG_LDO1_ACTIVE_DATA_DISABLE_V1_1_8V_V0_3_3V                       (0x27)
 #define RAA215300_REG_LDO1_ACTIVE_DATA_ENABLE_V1_1_8V_V0_3_3V                        (0x67)

 #define RAA215300_REG_LDO2_ACTIVE_DATA_DISABLE_V1_1_8V_V0_3_3V                       (0x27)
 #define RAA215300_REG_LDO2_ACTIVE_DATA_ENABLE_V1_1_8V_V0_3_3V                        (0x67)

 #define RAA215300_REG_MPIO1_CONFIG_DATA_ACTIVE_LOW_OPEN_DARAIN_NMOS_VR_EN_OUTPUT     (0x0e)
 #define RAA215300_REG_MPIO1_CONFIG_DATA_ACTIVE_HIGH_OPEN_DARAIN_NMOS_VR_EN_OUTPUT    (0x2e)

 #define RAA215300_REG_MPIO2_CONFIG_DATA_ACTIVE_LOW_OPEN_DARAIN_NMOS_VR_EN_OUTPUT     (0x0e)
 #define RAA215300_REG_MPIO2_CONFIG_DATA_ACTIVE_HIGH_OPEN_DARAIN_NMOS_VR_EN_OUTPUT    (0x2e)

 #define RAA215300_REG_MPIO3_CONFIG_DATA_EXTERNAL_VR_PGOOD_INPUT                      (0x02)

/* Defining Latency for Mode Transitions */
 #define TO_AWO_LDO_OFF_WAIT_MS                                                       (10)
 #define TO_AWO_MPIO2_OFF_WAIT_MS                                                     (10)
 #define TO_AWO_MPIO1_OFF_WAIT_MS                                                     (10)
 #define TO_ALLON_BUCK4_ON_WAIT_MS                                                    (3)
 #define TO_ALLON_MPIO1_ON_WAIT_MS                                                    (3)
 #define TO_ALLON_BUCK5_ON_WAIT_MS                                                    (10)

/*******************************************************************************************************************//**
 *  @brief       Change PMIC status from SLEEP to ACTIVE
 *  @param[IN]   None
 *  @retval      FSP_SUCCESS                  Successful transition to ACTIVE
 *  @retval      Any Other Error code apart from FSP_SUCCESS is  Unsuccessful open or start
 **********************************************************************************************************************/
fsp_err_t pmic_sleep_to_active (void)
{
    uint8_t   reg_address;
    uint8_t   reg_data = RESET_VALUE;
    fsp_err_t err      = FSP_SUCCESS;

    /* opening RIIC master module */
    g_i2c_master0.p_api->open(g_i2c_master0.p_ctrl, g_i2c_master0.p_cfg);

    /* handle error */
    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Open API failed ** \r\n");

        return err;
    }

    reg_address = RAA215300_REG_HW_REV_ADDR;
    pmic_read_reg(reg_address, &reg_data);
    APP_PRINT("HW REV addr:%x, data:%x\r\n", reg_address, reg_data);

    reg_address = RAA215300_REG_MPIO3_CONFIG_ADDR;
    pmic_read_reg(reg_address, &reg_data);
    APP_PRINT("MPIO3 Config addr:%x, data:%x\r\n", reg_address, reg_data);

    reg_address = RAA215300_REG_BLOCK_EN_ADDR;
    pmic_read_reg(reg_address, &reg_data);
    APP_PRINT("Block EN addr:%x, data:%x\r\n", reg_address, reg_data);

    APP_PRINT("Write to MPIO3 Config\r\n");

    reg_address = RAA215300_REG_MPIO3_CONFIG_ADDR;
    reg_data    = RAA215300_REG_MPIO3_CONFIG_DATA_EXTERNAL_VR_PGOOD_INPUT;
    pmic_write_reg(reg_address, reg_data);

    reg_address = RAA215300_REG_MPIO3_CONFIG_ADDR;
    pmic_read_reg(reg_address, &reg_data);
    APP_PRINT("MPIO3 Config addr:%x, data:%x\r\n", reg_address, reg_data);

    /* close open modules */
    g_i2c_master0.p_api->close(g_i2c_master0.p_ctrl);

    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Close API failed ** \r\n");
    }

    return err;
}

/*******************************************************************************************************************//**
 *  @brief       Change PMIC status from ALL_ON to AWO
 *
 *  @param[in]   None
 *
 *  @retval      FSP_SUCCESS                       successful event receiving returns FSP_SUCCESS
 *               err                               whichever occurs on either API or on I2C event failure
 **********************************************************************************************************************/
fsp_err_t pmic_allon_to_awo (void)
{
    uint8_t   reg_address;
    uint8_t   reg_data = RESET_VALUE;
    fsp_err_t err      = FSP_SUCCESS;

    /* opening RIIC master module */
    err = g_i2c_master0.p_api->open(g_i2c_master0.p_ctrl, g_i2c_master0.p_cfg);

    /* handle error */
    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Open API failed ** \r\n");

        return err;
    }

    APP_PRINT("Write to Config registers for AWO\r\n");

    /* PMIC_LDO1(VDD1833_SD0) OFF */
    reg_address = RAA215300_REG_LDO1_ACTIVE_ADDR;
    reg_data    = RAA215300_REG_LDO1_ACTIVE_DATA_DISABLE_V1_1_8V_V0_3_3V;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_LDO2(VDD1833_SD1) OFF */
    reg_address = RAA215300_REG_LDO2_ACTIVE_ADDR;
    reg_data    = RAA215300_REG_LDO2_ACTIVE_DATA_DISABLE_V1_1_8V_V0_3_3V;
    pmic_write_reg(reg_address, reg_data);

 #if BSP_CFG_RTOS == 2
    vTaskDelay(pdMS_TO_TICKS(TO_AWO_LDO_OFF_WAIT_MS));
 #else
    R_BSP_SoftwareDelay(TO_AWO_LDO_OFF_WAIT_MS, BSP_DELAY_UNITS_MILLISECONDS);
 #endif

    /* PMIC_Buck5(Ether_1V2) OFF */
    reg_address = RAA215300_REG_BUCK5_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK5_ENABLE_DATA_ABS_SLEEP;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_MPIO2 (DDR_VDDQLP_0.6V) Low */
    reg_address = RAA215300_REG_MPIO2_CONFIG_ADDR;
    reg_data    = RAA215300_REG_MPIO2_CONFIG_DATA_ACTIVE_LOW_OPEN_DARAIN_NMOS_VR_EN_OUTPUT;
    pmic_write_reg(reg_address, reg_data);

 #if BSP_CFG_RTOS == 2
    vTaskDelay(pdMS_TO_TICKS(TO_AWO_MPIO2_OFF_WAIT_MS));
 #else
    R_BSP_SoftwareDelay(TO_AWO_MPIO2_OFF_WAIT_MS, BSP_DELAY_UNITS_MILLISECONDS);
 #endif

    /* PMIC_MPIO1 (DDR_VDDQ_1.1V) Low */
    reg_address = RAA215300_REG_MPIO1_CONFIG_ADDR;
    reg_data    = RAA215300_REG_MPIO1_CONFIG_DATA_ACTIVE_LOW_OPEN_DARAIN_NMOS_VR_EN_OUTPUT;
    pmic_write_reg(reg_address, reg_data);

 #if BSP_CFG_RTOS == 2
    vTaskDelay(pdMS_TO_TICKS(TO_AWO_MPIO1_OFF_WAIT_MS));
 #else
    R_BSP_SoftwareDelay(TO_AWO_MPIO1_OFF_WAIT_MS, BSP_DELAY_UNITS_MILLISECONDS);
 #endif

    /* PMIC_Buck1 (VDD09_CA55) OFF */
    reg_address = RAA215300_REG_BUCK1_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK1_ENABLE_DATA_ABS;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_Buck3 (S1.8V) OFF */
    reg_address = RAA215300_REG_BUCK3_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK3_ENABLE_DATA_ABS;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_Buck4 (D3.3V) OFF */
    reg_address = RAA215300_REG_BUCK4_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK4_ENABLE_DATA_ABS_SLEEP;
    pmic_write_reg(reg_address, reg_data);

    /* close open modules */
    err = g_i2c_master0.p_api->close(g_i2c_master0.p_ctrl);

    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Close API failed ** \r\n");
    }

    return err;
}

/*******************************************************************************************************************//**
 *  @brief       Change PMIC status from AWO to ALL_ON
 *
 *  @param[in]   None
 *
 *  @retval      FSP_SUCCESS                       successful event receiving returns FSP_SUCCESS
 *               err                               whichever occurs on either API or on I2C event failure
 **********************************************************************************************************************/
fsp_err_t pmic_awo_to_allon (void)
{
    uint8_t   reg_address;
    uint8_t   reg_data = RESET_VALUE;
    fsp_err_t err      = FSP_SUCCESS;

    /* opening RIIC master module */
    err = g_i2c_master0.p_api->open(g_i2c_master0.p_ctrl, g_i2c_master0.p_cfg);

    /* handle error */
    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Open API failed ** \r\n");

        return err;
    }

    APP_PRINT("Write to Config registers for ALL_ON\r\n");

    /* PMIC_Buck1 (VDD09_CA55) ON */
    reg_address = RAA215300_REG_BUCK1_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK1_ENABLE_DATA_ABS_ACTIVE;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_Buck3 (S1.8V) ON */
    reg_address = RAA215300_REG_BUCK3_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK3_ENABLE_DATA_ABS_ACTIVE;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_Buck4 (D3.3V) ON */
    reg_address = RAA215300_REG_BUCK4_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK4_ENABLE_DATA_ABS_SLEEP_ACTIVE;
    pmic_write_reg(reg_address, reg_data);

 #if BSP_CFG_RTOS == 2
    vTaskDelay(pdMS_TO_TICKS(TO_ALLON_BUCK4_ON_WAIT_MS));
 #else
    R_BSP_SoftwareDelay(TO_ALLON_BUCK4_ON_WAIT_MS, BSP_DELAY_UNITS_MILLISECONDS);
 #endif

    /* PMIC_MPIO1 (DDR_VDDQ_1.1V) High */
    reg_address = RAA215300_REG_MPIO1_CONFIG_ADDR;
    reg_data    = RAA215300_REG_MPIO1_CONFIG_DATA_ACTIVE_HIGH_OPEN_DARAIN_NMOS_VR_EN_OUTPUT;
    pmic_write_reg(reg_address, reg_data);

 #if BSP_CFG_RTOS == 2
    vTaskDelay(pdMS_TO_TICKS(TO_ALLON_MPIO1_ON_WAIT_MS));
 #else
    R_BSP_SoftwareDelay(TO_ALLON_MPIO1_ON_WAIT_MS, BSP_DELAY_UNITS_MILLISECONDS);
 #endif

    /* PMIC_MPIO2 (DDR_VDDQLP_0.6V) High */
    reg_address = RAA215300_REG_MPIO2_CONFIG_ADDR;
    reg_data    = RAA215300_REG_MPIO2_CONFIG_DATA_ACTIVE_HIGH_OPEN_DARAIN_NMOS_VR_EN_OUTPUT;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_Buck5(Ether_1V2) ON */
    reg_address = RAA215300_REG_BUCK5_ENABLE_ADDR;
    reg_data    = RAA215300_REG_BUCK5_ENABLE_DATA_ABS_SLEEP_ACTIVE;
    pmic_write_reg(reg_address, reg_data);

 #if BSP_CFG_RTOS == 2
    vTaskDelay(pdMS_TO_TICKS(TO_ALLON_BUCK5_ON_WAIT_MS));
 #else
    R_BSP_SoftwareDelay(TO_ALLON_BUCK5_ON_WAIT_MS, BSP_DELAY_UNITS_MILLISECONDS);
 #endif

    /* PMIC_LDO1(VDD1833_SD0) ON */
    reg_address = RAA215300_REG_LDO1_ACTIVE_ADDR;
    reg_data    = RAA215300_REG_LDO1_ACTIVE_DATA_ENABLE_V1_1_8V_V0_3_3V;
    pmic_write_reg(reg_address, reg_data);

    /* PMIC_LDO2(VDD1833_SD1) ON */
    reg_address = RAA215300_REG_LDO2_ACTIVE_ADDR;
    reg_data    = RAA215300_REG_LDO2_ACTIVE_DATA_ENABLE_V1_1_8V_V0_3_3V;
    pmic_write_reg(reg_address, reg_data);

    /* close open modules */
    err = g_i2c_master0.p_api->close(g_i2c_master0.p_ctrl);

    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Close API failed ** \r\n");
    }

    return err;
}

/*******************************************************************************************************************//**
 *  @brief     Read PMIC Device Register
 *
 *  @param[in] reg_address                  register address to read
 *  @param[in] reg_data
 *
 *  @retval    FSP_SUCCESS                  on successful I2C transaction
 *             FSP_ERR_INVALID_POINTER      if invalid parameters passed
 *             err                          whichever occurs on either API or on I2C event failure
 **********************************************************************************************************************/
static fsp_err_t pmic_read_reg (uint8_t reg_address, uint8_t * reg_data)
{
    fsp_err_t err = FSP_SUCCESS;

    /* Parameter checking */
    if (NULL == reg_data)
    {
        err = FSP_ERR_INVALID_POINTER;
        APP_ERR_PRINT("** NULL Pointer check fail ** \r\n");

        return err;
    }

    /* Send register address to PMIC */
    err = g_i2c_master0.p_api->write(g_i2c_master0.p_ctrl, &reg_address, ONE_BYTE, true);

    /* handle error */
    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Write API failed ** \r\n");
    }
    else
    {
        err = validate_i2c_event();

        /* handle error */
        if (FSP_ERR_TRANSFER_ABORTED == err)
        {
            APP_ERR_PRINT("** Device register address, I2C write failed ** \r\n");
        }
        else
        {
            /* Read only when I2C write and its callback event is successful */
            err = g_i2c_master0.p_api->read(g_i2c_master0.p_ctrl, reg_data, ONE_BYTE, false);

            /* handle error */
            if (FSP_SUCCESS != err)
            {
                APP_ERR_PRINT("** R_RIIC_MASTER_Read API failed ** \r\n");

                // Do nothing, the error is returned in the end
            }
            else
            {
                err = validate_i2c_event();

                /* handle error */
                if (FSP_ERR_TRANSFER_ABORTED == err)
                {
                    APP_ERR_PRINT("** Device register read,  I2C read failed ** \r\n");
                }
            }
        }
    }

    /* On successful I2C transaction with PMOD-ACL return from here */
    return err;
}

/*******************************************************************************************************************//**
 *  @brief     Write PMIC Device Register
 *
 *  @param[in] reg_address                  register address to read
 *  @param[in] reg_data
 *
 *  @retval    FSP_SUCCESS                  on successful I2C transaction
 *             FSP_ERR_INVALID_POINTER      if invalid parameters passed
 *             err                          whichever occurs on either API or on I2C event failure
 **********************************************************************************************************************/
static fsp_err_t pmic_write_reg (uint8_t reg_address, uint8_t reg_data)
{
    fsp_err_t err = FSP_SUCCESS;
    uint8_t   buf[2];

    buf[0] = reg_address;
    buf[1] = reg_data;

    /* Send register address to PMIC */
    err = g_i2c_master0.p_api->write(g_i2c_master0.p_ctrl, &buf[0], 2, false);

    /* handle error */
    if (FSP_SUCCESS != err)
    {
        APP_ERR_PRINT("** R_RIIC_MASTER_Write API failed ** \r\n");
    }
    else
    {
        err = validate_i2c_event();

        /* handle error */
        if (FSP_ERR_TRANSFER_ABORTED == err)
        {
            APP_ERR_PRINT("** Device register address, I2C write failed ** \r\n");
        }
    }

    /* On successful I2C transaction with PMOD-ACL return from here */
    return err;
}

/*******************************************************************************************************************//**
 *  @brief      User callback function
 *  @param[in]  p_args
 *  @retval None
 **********************************************************************************************************************/
void i2c_master_callback (i2c_master_callback_args_t * p_args)
{
    if (NULL != p_args)
    {
        /* capture callback event for validating the i2c transfer event*/
        i2c_event = p_args->event;
    }
}

/*******************************************************************************************************************//**
 *  @brief       Validate i2c receive/transmit  based on required write read operation
 *
 *  @param[in]   None
 *
 *  @retval      FSP_SUCCESS                       successful event receiving returns FSP_SUCCESS
 *               FSP_ERR_TRANSFER_ABORTED          Either on timeout elapsed or received callback event is
 *                                                 I2C_MASTER_EVENT_ABORTED
 **********************************************************************************************************************/
static fsp_err_t validate_i2c_event (void)
{
    uint64_t local_time_out = UINT64_MAX;

    /* resetting call back event capture variable */
    i2c_event = (i2c_master_event_t) RESET_VALUE;

    do
    {
        /* This is to avoid infinite  loop */
        --local_time_out;

        if (RESET_VALUE == local_time_out)
        {
            return FSP_ERR_TRANSFER_ABORTED;
        }
    } while (i2c_event == RESET_VALUE);

    if (i2c_event != I2C_MASTER_EVENT_ABORTED)
    {
        i2c_event = (i2c_master_event_t) RESET_VALUE; // Make sure this is always Reset before return
        return FSP_SUCCESS;
    }

    i2c_event = (i2c_master_event_t) RESET_VALUE;     // Make sure this is always Reset before return
    return FSP_ERR_TRANSFER_ABORTED;
}

#endif                                                /*defined(BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT) && (BSP_FEATURE_BSP_HAS_CM33BOOT_SUPPORT == 1)*/

/*******************************************************************************************************************//**
 * @} (end addtogroup r_riic_master_pmic)
 **********************************************************************************************************************/
