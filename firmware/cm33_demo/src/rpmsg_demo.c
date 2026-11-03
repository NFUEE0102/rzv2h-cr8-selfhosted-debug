/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include "FreeRTOS.h"
#include "openamp/open_amp.h"
#include "platform_info.h"
#include "rsc_table.h"

extern int  init_system(void);
extern void cleanup_system(void);

#define SHUTDOWN_MSG     (0xEF56A55A)

/* Local variables */

/*-----------------------------------------------------------------------------*
 *  RPMSG callbacks setup by remoteproc_resource_init()
 *-----------------------------------------------------------------------------*/

/* Local variables */

static struct rpmsg_endpoint rp_ept[CFG_RPMSG_SVCNO] = {0};

volatile static int evt_svc_unbind[CFG_RPMSG_SVCNO] = {0};

/**
 *  Callback Function: rpmsg_endpoint_cb
 *
 *  @param[in] rp_svc
 *  @param[in] data
 *  @param[in] len
 *  @param[in] priv
 *  @param[in] src
 */
static int rpmsg_endpoint_cb0 (struct rpmsg_endpoint * cb_rp_ept, void * data, size_t len, uint32_t src, void * priv)
{
    /* service 0 */
    (void) priv;
    (void) src;

    /* On reception of a shutdown we signal the application to terminate */
    if ((*(unsigned int *) data) == SHUTDOWN_MSG)
    {
        evt_svc_unbind[0] = 1;

        return RPMSG_SUCCESS;
    }

    /* Send data back to master */
    if (rpmsg_send(cb_rp_ept, data, (int) len) < 0)
    {
        LPERROR("rpmsg_send failed\n");

        return -1;
    }

    return RPMSG_SUCCESS;
}

static int rpmsg_endpoint_cb1 (struct rpmsg_endpoint * cb_rp_ept, void * data, size_t len, uint32_t src, void * priv)
{
    /* service 1 */
    (void) priv;
    (void) src;

    /* On reception of a shutdown we signal the application to terminate */
    if ((*(unsigned int *) data) == SHUTDOWN_MSG)
    {
        evt_svc_unbind[1] = 1;

        return RPMSG_SUCCESS;
    }

    /* Send data back to master */
    if (rpmsg_send(cb_rp_ept, data, (int) len) < 0)
    {
        LPERROR("rpmsg_send failed\n");

        return -1;
    }

    return RPMSG_SUCCESS;
}

/**
 *  Callback Function: rpmsg_service_unbind
 *
 *  @param[in] ept
 */
static void rpmsg_service_unbind0 (struct rpmsg_endpoint * ept)
{
    (void) ept;

    /* service 0 */
    rpmsg_destroy_ept(&rp_ept[0]);
    memset(&rp_ept[0], 0x0, sizeof(struct rpmsg_endpoint));
    evt_svc_unbind[0] = 1;
}

static void rpmsg_service_unbind1 (struct rpmsg_endpoint * ept)
{
    (void) ept;

    /* service 1 */
    rpmsg_destroy_ept(&rp_ept[1]);
    memset(&rp_ept[1], 0x0, sizeof(struct rpmsg_endpoint));
    evt_svc_unbind[1] = 1;
}

/*-----------------------------------------------------------------------------*
 *  Application
 *-----------------------------------------------------------------------------*/
int app (struct rpmsg_device * rdev, void * platform, unsigned long svcno)
{
    (void) platform;
    int ret;

    if (svcno == 0UL)
    {
        ret = rpmsg_create_ept(&rp_ept[0],
                               rdev,
                               CFG_RPMSG_SVC_NAME0,
                               APP_EPT_ADDR,
                               RPMSG_ADDR_ANY,
                               rpmsg_endpoint_cb0,
                               rpmsg_service_unbind0);
        if (ret)
        {
            LPERROR("Failed to create endpoint.\n");

            return -1;
        }
    }
    else
    {
        ret = rpmsg_create_ept(&rp_ept[1],
                               rdev,
                               CFG_RPMSG_SVC_NAME1,
                               APP_EPT_ADDR,
                               RPMSG_ADDR_ANY,
                               rpmsg_endpoint_cb1,
                               rpmsg_service_unbind1);
        if (ret)
        {
            LPERROR("Failed to create endpoint.\n");

            return -1;
        }
    }
    
    LPRINTF("Waiting for events...\n");
    while (1)
    {
        vTaskDelay(0);

        /* we got a shutdown request, exit */
        if (evt_svc_unbind[svcno])
        {
            break;
        }
    }

    /* Clear shutdown flag */
    evt_svc_unbind[svcno] = 0;

    return 0;
}
