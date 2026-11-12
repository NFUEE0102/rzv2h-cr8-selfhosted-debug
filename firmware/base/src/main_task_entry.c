/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include "main_task.h"
/* Main Task entry function */
/* pvParameters contains TaskHandle_t */
#include "openamp/open_amp.h"
#include "platform_info.h"
#include "rsc_table.h"
#include "r8_blackbox.h"

#define RECONNECT_FLG    (1)           /* 1:reconnect after exit, 0:disconnect after exit */
#define RECONNECT_DLY    (10000u)

extern int app (struct rpmsg_device * rdev, void * platform, unsigned long svcno);


void main_task_entry(void *pvParameters)
{
    unsigned long         proc_id = *((unsigned long*)pvParameters);
    unsigned long         rsc_id  = *((unsigned long*)pvParameters);
    struct rpmsg_device * rpdev;
    void                * platform;
    int ret;

    R8_BB_STAGE(3);

    ret = init_system();
    if (ret)
    {
        LPERROR("Failed to init remoteproc device.\n");
        goto err1;
    }

    R8_BB_STAGE(4);
    ret = platform_init(proc_id, rsc_id, &platform);
    if (ret)
    {
        LPERROR("Failed to create remoteproc device.\n");
        goto err1;
    }
    else
    {
        do
        {
            /* RTOS is Master, but this setting must remote in this release. */
            R8_BB_STAGE(6);
            rpdev = platform_create_rpmsg_vdev(platform, 0x0U, VIRTIO_DEV_DEVICE, NULL, NULL);
            R8_BB_STAGE(7);
            if (!rpdev)
            {
                LPERROR("Fail, platform_create_rpmsg_vdev.\n");
                metal_log(METAL_LOG_INFO, "Fail, platform_create_rpmsg_vdev.");
                goto err2;
            }

            /* Kick the application */
            R8_BB_STAGE(8);
            (void) app(rpdev, platform, proc_id);

            LPRINTF("De-initializating remoteproc\n");
            platform_release_rpmsg_vdev(platform, rpdev);

            vTaskDelay(RECONNECT_DLY);
        } while (RECONNECT_FLG);
    }

err2:
    platform_cleanup(platform);
err1:
    vTaskDelete(NULL);
}
