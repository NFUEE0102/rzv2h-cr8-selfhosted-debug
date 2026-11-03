/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#ifndef CR8_START_H_
#define CR8_START_H_

typedef struct
{
    uint32_t src_addr_bsp;
    uint32_t dst_addr_bsp;
    uint32_t size_bsp;
    uint32_t src_addr_bsp_inv;
    uint32_t dst_addr_bsp_inv;
    uint32_t size_bsp_inv;
    uint32_t src_addr_usr_sram;
    uint32_t dst_addr_usr_sram;
    uint32_t size_usr_sram;
    uint32_t src_addr_usr_sram_inv;
    uint32_t dst_addr_usr_sram_inv;
    uint32_t size_usr_sram_inv;
    uint32_t src_addr_usr_sdram;
    uint32_t dst_addr_usr_sdram;
    uint32_t size_usr_sdram;
    uint32_t src_addr_usr_sdram_inv;
    uint32_t dst_addr_usr_sdram_inv;
    uint32_t size_usr_sdram_inv;
    uint32_t init_wait_data_addr;
    uint32_t init_wait_data;
    uint8_t  reserved[428];
} cr8_header_t;

typedef struct
{
    uint32_t ca_address;
    uint32_t cm_address;
    uint32_t size;
} ca_cm_address_convert_table_t;

#define CR8_CORE_NUM                       (2)
#define CR8_HEADER_ADDR_CR8_0              (0x60200000)
#define CR8_HEADER_ADDR_CR8_1              (0x61300000)

#define CR8_CORE0_RESET_VECTOR_ADDRESS     (0x42040000)
#define CR8_CORE1_RESET_VECTOR_ADDRESS     (0x42080000)

#define ADDRESS_CM_SRAM_SECURE_BASE        (0x00000000)
#define ADDRESS_CM_SRAM_NONSECURE_BASE     (0x10000000)
#define ADDRESS_CA_SRAM_BASE               (0x00000000)
#define SRAM_SIZE                          (0x10000000)

#define ADDRESS_CM_IOREG_SECURE_BASE       (0x40000000)
#define ADDRESS_CM_IOREG_NONSECURE_BASE    (0x50000000)
#define ADDRESS_CA_IOREG_BASE              (0x10000000)
#define IOREG_SIZE                         (0x10000000)

#define ADDRESS_CM_SPI_SECURE_BASE         (0x60000000)
#define ADDRESS_CM_SPI_NONSECURE_BASE      (0x70000000)
#define ADDRESS_CA_SPI_BASE                (0x20000000)
#define SPI_SIZE                           (0x10000000)

#define ADDRESS_CM_DDR_SECURE_BASE         (0x80000000)
#define ADDRESS_CM_DDR_NONSECURE_BASE      (0x90000000)
#define ADDRESS_CA_DDR_BASE                (0x40000000)
#define DDR_SIZE                           (0x10000000)

#define ADDRESS_TABLE_END                  (0xFFFFFFFF)

void     copy_cr8_prog(void);
void     release_reset_cr8(void);
uint32_t convert_addr_cr_to_cm(uint32_t original_address);

#endif
