/***********************************************************************************************************************
 * Copyright [2020-2021] Renesas Electronics Corporation and/or its affiliates.  All Rights Reserved.
 *
 * This software and documentation are supplied by Renesas Electronics Corporation and/or its affiliates and may only
 * be used with products of Renesas Electronics Corp. and its affiliates ("Renesas").  No other uses are authorized.
 * Renesas products are sold pursuant to Renesas terms and conditions of sale.  Purchasers are solely responsible for
 * the selection and use of Renesas products and Renesas assumes no liability.  No license, express or implied, to any
 * intellectual property right is granted by Renesas.  This software is protected under all applicable laws, including
 * copyright laws. Renesas reserves the right to change or discontinue this software and/or this documentation.
 * THE SOFTWARE AND DOCUMENTATION IS DELIVERED TO YOU "AS IS," AND RENESAS MAKES NO REPRESENTATIONS OR WARRANTIES, AND
 * TO THE FULLEST EXTENT PERMISSIBLE UNDER APPLICABLE LAW, DISCLAIMS ALL WARRANTIES, WHETHER EXPLICITLY OR IMPLICITLY,
 * INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT, WITH RESPECT TO THE
 * SOFTWARE OR DOCUMENTATION.  RENESAS SHALL HAVE NO LIABILITY ARISING OUT OF ANY SECURITY VULNERABILITY OR BREACH.
 * TO THE MAXIMUM EXTENT PERMITTED BY LAW, IN NO EVENT WILL RENESAS BE LIABLE TO YOU IN CONNECTION WITH THE SOFTWARE OR
 * DOCUMENTATION (OR ANY PERSON OR ENTITY CLAIMING RIGHTS DERIVED FROM YOU) FOR ANY LOSS, DAMAGES, OR CLAIMS WHATSOEVER,
 * INCLUDING, WITHOUT LIMITATION, ANY DIRECT, CONSEQUENTIAL, SPECIAL, INDIRECT, PUNITIVE, OR INCIDENTAL DAMAGES; ANY
 * LOST PROFITS, OTHER ECONOMIC DAMAGE, PROPERTY DAMAGE, OR PERSONAL INJURY; AND EVEN IF RENESAS HAS BEEN ADVISED OF THE
 * POSSIBILITY OF SUCH LOSS, DAMAGES, CLAIMS OR COSTS.
 **********************************************************************************************************************/
/**
 * @file    sys_init.c
 * @brief   Metal device definitions
 * @date    2020.10.15
 * @author  Copyright (c) 2020, eForce Co., Ltd. All rights reserved.
 *
 ****************************************************************************
 * @par     History
 *          - rev 1.0 (2020.10.15) Imada
 *            First release
 ****************************************************************************
 */

#include "metal/io.h"
#include "metal/device.h"
#include "metal/sys.h"
#include "FreeRTOS.h"
#include "rsc_table.h"
#include "platform_info.h"
#include "bsp_api.h"

extern void init_resource_table(void);

const metal_phys_addr_t metal_phys[] =
{
    MBX_REG_PA,
    CFG_RSCTBL_MEM_PA,
    CFG_VRING0_BASE0_PA,
    CFG_VRING0_BASE1_PA,
    CFG_VRING_SHM_BASE0_PA,
    CFG_VRING_SHM_BASE1_PA,
};

struct metal_device metal_dev_table[] =
{
    /* Mailbox device */
    {
        MBX_DEV_NAME,
        NULL,
        1,
        {
            {
                (void *) MBX_REG_VA,
                &metal_phys[0],
                MBX_MAP_SIZE,
                (sizeof(metal_phys_addr_t) << 3),
                (metal_phys_addr_t) (-1),
                0,
                {NULL}
            }
        },
        {NULL},
        1,
        (void *) MBX_INT_NUM,
    },

    /* Resource table */
    {
        CFG_RSCTBL_DEV_NAME,
        NULL,
        1,
        {
            {
                (void *) (CFG_RSCTBL_MEM_VA),
                &metal_phys[1],
                CFG_RSCTBL_MAP_SIZE,
                (sizeof(metal_phys_addr_t) << 3),
                (unsigned long) (-1),
                0,
                {NULL},
            }
        },
        {NULL},
        0,
        NULL,
    },

    /* RPMSG (vring) */
    {                                  /* vring #0 CTL */
        CFG_VRING_CTL_NAME0,
        NULL,
        1,
        {
            {
                (void *) (CFG_VRING0_BASE0_VA),
                &metal_phys[2],
                CFG_VRING_SIZE0,
                (sizeof(metal_phys_addr_t) << 3),
                (unsigned long) (-1),
                0,
                {NULL},
            }
        },
        {NULL},
        0,
        NULL,
    },
    {                                  /* vring #1 CTL */
        CFG_VRING_CTL_NAME1,
        NULL,
        1,
        {
            {
                (void *) (CFG_VRING0_BASE1_VA),
                &metal_phys[3],
                CFG_VRING_SIZE1,
                (sizeof(metal_phys_addr_t) << 3),
                (unsigned long) (-1),
                0,
                {NULL},
            }
        },
        {NULL},
        0,
        NULL,
    },
    {                                  /* vring #0 SHM */
        CFG_VRING_SHM_NAME0,
        NULL,
        1,
        {
            {
                (void *) (CFG_VRING_SHM_BASE0_VA),
                &metal_phys[4],
                CFG_VRING_SHM_SIZE0,
                (sizeof(metal_phys_addr_t) << 3),
                (unsigned long) (-1),
                0,
                {NULL},
            }
        },
        {NULL},
        0,
        NULL,
    },
    {                                  /* vring #1 SHM */
        CFG_VRING_SHM_NAME1,
        NULL,
        1,
        {
            {
                (void *) (CFG_VRING_SHM_BASE1_VA),
                &metal_phys[5],
                CFG_VRING_SHM_SIZE1,
                (sizeof(metal_phys_addr_t) << 3),
                (unsigned long) (-1),
                0,
                {NULL},
            }
        },
        {NULL},
        0,
        NULL,
    },
};

int init_system (void)
{
    unsigned int             i;
    int                      ret;
    struct metal_init_params metal_param = METAL_INIT_DEFAULTS;
    struct metal_device    * dev;

    init_resource_table();

    ret = metal_init(&metal_param);
    if (ret)
    {
        return ret;
    }

    /* register device */
    for (i = 0U; i < (sizeof(metal_dev_table) / sizeof(struct metal_device)); i++)
    {
        dev = &metal_dev_table[i];
        ret = metal_register_generic_device(dev);
        if (ret)
        {
            break;
        }
    }

    return ret;
}

void cleanup_system (void)
{
    metal_finish();
}
