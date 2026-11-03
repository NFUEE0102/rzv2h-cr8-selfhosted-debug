/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#ifndef I2C_PMIC_H_
#define I2C_PMIC_H_

/* generic headers */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "hal_data.h"

#define LVL_ERR        (1u)            /* error conditions   */

#define RESET_VALUE    (0x00)

#define APP_PRINT(fn_, ...)

#define APP_ERR_PRINT(fn_, ...)

#define ONE_BYTE    0x01
#define TWO_BYTE    0x02

/*
 * function declarations
 */
fsp_err_t pmic_sleep_to_active(void);
fsp_err_t pmic_allon_to_awo(void);
fsp_err_t pmic_awo_to_allon(void);

fsp_err_t pd_all_on_preproc(void);
fsp_err_t pd_all_on(void);
fsp_err_t pd_all_on_postproc(void);
fsp_err_t pd_all_on_postproc_axi(void);

#endif                                 /* I2C_PMIC_H_ */
