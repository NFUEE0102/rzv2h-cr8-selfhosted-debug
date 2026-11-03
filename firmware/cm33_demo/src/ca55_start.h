/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#ifndef CA55_START_H_
#define CA55_START_H_

#define CA55_RESET_VECTOR_ADDRESS    (0x08103000)

#define RZV2H_XSPI_MEMORY_MAP_BASE 0x60000000
#define RZV2H_SPIROM_BL2_BASE      (RZV2H_XSPI_MEMORY_MAP_BASE + 0x00100000)
#define RZV2H_SPIROM_BL2_LIMIT     (RZV2H_XSPI_MEMORY_MAP_BASE + 0x00160000)
#define RZV2H_SPIROM_BOOTPARM_SIZE (0x200)
#define BL2_BASE RZV2H_SPIROM_BL2_BASE
#define BL2_LIMIT RZV2H_SPIROM_BL2_LIMIT
#define BL2_BOOTPARM_SIZE RZV2H_SPIROM_BOOTPARM_SIZE
#define RZV2H_BL2_SIZE_MAX         (BL2_LIMIT - BL2_BASE)          /* This value is not checked/enforced anywhwere */

void stop_ca55(void);
void release_reset_ca55(void);
void load_ca55_prog (void);

#endif
