/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include <stdio.h>
#include "hal_data.h"
#include "cr8_start.h"

uint8_t cr8_dummy_program[] =
{
    0x18, 0xf0, 0x9f, 0xe5, 0x18, 0xf0, 0x9f, 0xe5, 0x18, 0xf0, 0x9f, 0xe5, 0x18, 0xf0, 0x9f, 0xe5,
    0x18, 0xf0, 0x9f, 0xe5, 0x18, 0xf0, 0x9f, 0xe5, 0x18, 0xf0, 0x9f, 0xe5, 0x18, 0xf0, 0x9f, 0xe5,
    0x44, 0x00, 0x00, 0x00, 0x41, 0x00, 0x00, 0x00, 0x41, 0x00, 0x00, 0x00, 0x41, 0x00, 0x00, 0x00,
    0x41, 0x00, 0x00, 0x00, 0x41, 0x00, 0x00, 0x00, 0x41, 0x00, 0x00, 0x00, 0x41, 0x00, 0x00, 0x00,
    0x00, 0xBE, 0x70, 0x47, 0xFE, 0xFF, 0xFF, 0xEB,
};

uint32_t convert_addr_cr_to_cm (uint32_t original_address)
{
    uint32_t cm_address = original_address; // Set unconverted address as initial value.
    uint32_t table_num;
    ca_cm_address_convert_table_t convert_table[] =
    {
        {ADDRESS_CA_SRAM_BASE,  ADDRESS_CM_SRAM_SECURE_BASE,  SRAM_SIZE                              },
        {ADDRESS_CA_IOREG_BASE, ADDRESS_CM_IOREG_SECURE_BASE, IOREG_SIZE                             },
        {ADDRESS_CA_SPI_BASE,   ADDRESS_CM_SPI_SECURE_BASE,   SPI_SIZE                               },
        {ADDRESS_CA_DDR_BASE,   ADDRESS_CM_DDR_SECURE_BASE,   DDR_SIZE                               },
        {ADDRESS_TABLE_END,     ADDRESS_TABLE_END,            ADDRESS_TABLE_END                      }
    };

    for (table_num = 0;
         ((table_num < (sizeof(convert_table) / sizeof(ca_cm_address_convert_table_t))) &&
          ADDRESS_TABLE_END != convert_table[table_num].size);
         table_num++)
    {
        uint32_t region_base = convert_table[table_num].ca_address;
        if ((region_base <= original_address) && (original_address < (region_base + convert_table[table_num].size)))
        {
            /* find region: convert address */
            cm_address = (original_address & (convert_table[table_num].size - 1)) | convert_table[table_num].cm_address;

            /* exit loop */
            break;
        }
    }

    return cm_address;
}

void copy_cr8_prog (void)
{
    cr8_header_t * header;
    fsp_err_t      err;
    uint32_t       i;
    uint32_t       header_addr[CR8_CORE_NUM]  = {CR8_HEADER_ADDR_CR8_0, CR8_HEADER_ADDR_CR8_1};
    uint32_t       cr8_vec_addr[CR8_CORE_NUM] = {CR8_CORE0_RESET_VECTOR_ADDRESS, CR8_CORE1_RESET_VECTOR_ADDRESS};

    for (i = 0; i < CR8_CORE_NUM; i++)
    {
        err    = FSP_SUCCESS;
        header = (cr8_header_t *) header_addr[i];

        if ((~(header->src_addr_bsp) != header->src_addr_bsp_inv) ||
            (~(header->dst_addr_bsp) != header->dst_addr_bsp_inv) || (~(header->size_bsp) != header->size_bsp_inv))
        {
            err = FSP_ERR_INVALID_DATA;
        }

        if (FSP_SUCCESS != err)
        {
            if ((~(header->src_addr_usr_sram) != header->src_addr_usr_sram_inv) ||
                (~(header->dst_addr_usr_sram) != header->dst_addr_usr_sram_inv) ||
                (~(header->size_usr_sram) != header->size_usr_sram_inv))
            {
                err = FSP_ERR_INVALID_DATA;
            }
        }

        if (FSP_SUCCESS != err)
        {
            if ((~(header->src_addr_usr_sdram) != header->src_addr_usr_sdram_inv) ||
                (~(header->dst_addr_usr_sdram) != header->dst_addr_usr_sdram_inv) ||
                (~(header->size_usr_sdram) != header->size_usr_sdram_inv))
            {
                err = FSP_ERR_INVALID_DATA;
            }
        }

        if (FSP_SUCCESS == err)
        {
            /* Write CR8 BSP data to ITCM */
            if (0 != header->size_bsp)
            {
                memcpy((uint8_t *) convert_addr_cr_to_cm(header->dst_addr_bsp),
                       (uint8_t *) convert_addr_cr_to_cm(header->src_addr_bsp), header->size_bsp);
            }

            /* Write CR8 data to SRAM */
            if (0 != header->size_usr_sram)
            {
                memcpy((uint8_t *) convert_addr_cr_to_cm(header->dst_addr_usr_sram),
                       (uint8_t *) convert_addr_cr_to_cm(header->src_addr_usr_sram), header->size_usr_sram);
            }

            /* Write CR8 data to SDRAM */
            if (0 != header->size_usr_sdram)
            {
                memcpy((uint8_t *) convert_addr_cr_to_cm(header->dst_addr_usr_sdram),
                       (uint8_t *) convert_addr_cr_to_cm(header->src_addr_usr_sdram), header->size_usr_sdram);
            }

            /* Writing data for initialization wait */
            memcpy((uint8_t *) convert_addr_cr_to_cm(header->init_wait_data_addr),
                   (uint8_t *) &header->init_wait_data,
                   sizeof(uint32_t));
        }
        else
        {
            memcpy((uint8_t *) cr8_vec_addr[i], cr8_dummy_program, sizeof(cr8_dummy_program));
        }
    }
}
