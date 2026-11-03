/***********************************************************************************************************************
l * Copyright [2020-2021] Renesas Electronics Corporation and/or its affiliates.  All Rights Reserved.
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
 * @file    rsc_table.c
 * @brief   The remote resource table.
 * @date    2020.10.20
 * @author  Copyright (c) 2020, eForce Co., Ltd. All rights reserved.
 *
 ****************************************************************************
 * @par     History
 *          - rev 1.0 (2020.10.20) Imada
 *            First release for RZ/V2
 ****************************************************************************
 */

#include "rsc_table.h"

#ifdef __ICCARM__
 #pragma location=".resource_table"
struct remote_resource_table resources[2];
#else
struct remote_resource_table __resource resources[2];
#endif

struct remote_resource_table resources_init[] =
{
    {
        /* Version */
        1,

        /* NUmber of table entries */
        NUM_TABLE_ENTRIES,

        /* reserved fields */
        {0,                   0},

        /* Offsets of rsc entries */
        {
            offsetof(struct remote_resource_table, rproc_mem),
            offsetof(struct remote_resource_table, rpmsg_vdev)
        },

        {RSC_RPROC_MEM,       RPMSG_MEM_BASE, RPMSG_MEM_BASE, RPMSG_MEM_SIZE, 0},

#ifdef __ICCARM__

        /* Virtio device entry */
        {
            RSC_VDEV, VIRTIO_ID_RPMSG_, VRING_NOTIFYID0, RPMSG_IPU_C0_FEATURES, 0, 0, 0,
            NUM_VRINGS,{0,                   0},
            {
                /* Vring rsc entry - part of vdev rsc entry */
                {CFG_VRING0_BASE0_PA, CFG_VRING_ALIGN0, CFG_RPMSG_NUM_BUFS0, 0, 0},
                {CFG_VRING1_BASE0_PA, CFG_VRING_ALIGN0, CFG_RPMSG_NUM_BUFS0, 0, 0}
            }
        }
#else

        /* Virtio device entry */
        {
            RSC_VDEV, VIRTIO_ID_RPMSG_, 0, RPMSG_IPU_C0_FEATURES, 0, 0, 0,
            NUM_VRINGS,{0,                   0},
        },

        /* Vring rsc entry - part of vdev rsc entry */
        {CFG_VRING0_BASE0_PA, CFG_VRING_ALIGN0, CFG_RPMSG_NUM_BUFS0, 0, 0},
        {CFG_VRING1_BASE0_PA, CFG_VRING_ALIGN0, CFG_RPMSG_NUM_BUFS0, 0, 0}
#endif
    },
    {
        /* Version */
        1,

        /* NUmber of table entries */
        NUM_TABLE_ENTRIES,

        /* reserved fields */
        {0,                   0},

        /* Offsets of rsc entries */
        {
            offsetof(struct remote_resource_table, rproc_mem),
            offsetof(struct remote_resource_table, rpmsg_vdev)
        },

        {RSC_RPROC_MEM,       RPMSG_MEM_BASE, RPMSG_MEM_BASE, RPMSG_MEM_SIZE, 0},

#ifdef __ICCARM__

        /* Virtio device entry */
        {
            RSC_VDEV, VIRTIO_ID_RPMSG_, VRING_NOTIFYID1, RPMSG_IPU_C0_FEATURES, 0, 0, 0,
            NUM_VRINGS,{0,                   0},
            {
                /* Vring rsc entry - part of vdev rsc entry */
                {CFG_VRING0_BASE1_PA, CFG_VRING_ALIGN1, CFG_RPMSG_NUM_BUFS1, 1, 0},
                {CFG_VRING1_BASE1_PA, CFG_VRING_ALIGN1, CFG_RPMSG_NUM_BUFS1, 1, 0}
            }
        }
#else

        /* Virtio device entry */
        {
            RSC_VDEV, VIRTIO_ID_RPMSG_, 0, RPMSG_IPU_C0_FEATURES, 0, 0, 0,
            NUM_VRINGS,{0,                   0},
        },

        /* Vring rsc entry - part of vdev rsc entry */
        {CFG_VRING0_BASE1_PA, CFG_VRING_ALIGN1, CFG_RPMSG_NUM_BUFS1, 1, 0},
        {CFG_VRING1_BASE1_PA, CFG_VRING_ALIGN1, CFG_RPMSG_NUM_BUFS1, 1, 0}
#endif
    },
};

void init_resource_table (void)
{
    memcpy(resources, resources_init, sizeof(resources_init));
}

void * get_resource_table (int rsc_id, unsigned int * len)
{
    *len = sizeof(resources[rsc_id]);

    return (void *) &resources[rsc_id];
}
