/*
* Copyright (c) 2020 - 2024 Renesas Electronics Corporation and/or its affiliates
*
* SPDX-License-Identifier: BSD-3-Clause
*/

#include <metal/atomic.h>
#include <metal/assert.h>
#include <metal/device.h>
#include <metal/irq.h>
#include <metal/list.h>
#include <metal/utilities.h>
#include <openamp/rpmsg_virtio.h>
#include "platform_info.h"
#include "semphr.h"
#include "hal_data.h"
#include "r8_blackbox.h"


extern struct ipi_info ipi;

/* Inline functions to add accessing address check to corresponding
 * libmetal functions to avoid accessing a reserved region.
 * They are mainly required because of larger (uio) mmap size due the
 * 4KB page size on Verified Linux. They are also utilized for FreeRTOS because
 * accessing a reserved area of registers can cause system failure.
 */
static int init_memory_device (struct remoteproc * rproc, struct shm_info * info) {
    struct metal_device * dev;
    metal_phys_addr_t     mem_pa;
    int ret;

    ret = metal_device_open(info->bus_name, info->name, &dev);
    if (ret)
    {
        LPERROR("Failed to open uio device %s: %d.\n", info->name, ret);
        goto err;
    }

    LPRINTF("Successfully open uio device: %s.\n", info->name);

    info->dev = dev;
    info->io  = metal_device_io_region(dev, 0x0U);
    if (!info->io)
    {
        goto err;
    }

    mem_pa = metal_io_phys(info->io, 0x0U);
    remoteproc_init_mem(&info->mem, info->name, mem_pa, mem_pa, metal_io_region_size(info->io), info->io);
    remoteproc_add_mem(rproc, &info->mem);
    LPRINTF("Successfully added memory device %s.\n", info->name);

    return 0;
err:
    if (info->dev)
    {
        metal_device_close(info->dev);
    }

    return ret;
}


/* ---- one-way timestamp instrumentation (2026-08-13, doc 13 §5.7) ---- */
#define IPCTS_GTCNT   (*(volatile unsigned int *)0x13010648U)
volatile unsigned int g_ipcts_isr  = 0U;  /* T1: MHU ISR entry */
volatile unsigned int g_ipcts_task = 0U;  /* T2: rproc task woken from semaphore */
volatile unsigned int g_ipcts_cb   = 0U;  /* T3: rpmsg endpoint callback entry */

static void rzv2_mhu_callback (mhu_callback_args_t * p_args)
{
    unsigned int         val = 0U;
    signed portBASE_TYPE xHigherPriorityTaskWoken;

    g_ipcts_isr = IPCTS_GTCNT;   /* T1 */

    /* Clear the interrupt: Already done by MHU driver */

    /* Get a massage from the mailbox */
    LPRINTF("rzv2_mhu_callback\n");
    val = p_args->msg;
    if (val >= RSC_MAX_NUM)            /* val should have the notify_id of the sender */
    {
        return;  /* Invalid message arrived */
    }

#ifdef __linux__
    ipi.notify_id = val;
    atomic_flag_clear(&ipi.sync);
#else                                  /* FreeRTOS */
    if (ipi.ipi_sem_id[val] != NULL)
    {
        R8_BB_INC(mhu_isr);
        R8_BB_INC(sem_give);
        xSemaphoreGiveFromISR(ipi.ipi_sem_id[val], &xHigherPriorityTaskWoken);
    }
    else
    {
        return;
    }
#endif

    return;
}

static int rzv2_enable_interrupt (struct remoteproc * rproc, struct metal_device * ipi_dev)
{
    unsigned int irq_vect;
    int          ret = 0;

    if (!ipi.registered)
    {
        /* RZ FSP 4.3.0 (upstream libmetal 2023): the MHU driver's metal_irq_isr_wrapper() hands the
         * interrupt to R_MHU_B_NS_IsrSub() through metal_irq_handle() itself, and R_MHU_B_NS_Open()
         * already did R_BSP_IrqCfgEnable(). libmetal's metal_irq_register()/metal_irq_enable() now
         * route through an IRQ controller this port does not register, so nothing is left to do
         * here (the 3.x code registered R_MHU_B_NS_IsrSub with libmetal's per-IRQ handler list). */
        irq_vect = (uintptr_t) ipi_dev->irq_info;
        (void) rproc;
        LPRINTF("MHU irq %u handled by the FSP driver\n", (unsigned int) irq_vect);
    }

    return ret;
}

static void rzv2_disable_interrupt (struct remoteproc * rproc)
{
    (void) rproc;
    struct metal_device * dev;
    int ret;

    dev = ipi.dev;
    if (dev)
    {
        /* The MHU driver owns the interrupt (see rzv2_enable_interrupt); R_MHU_B_NS_Close() disables it. */
        ret = 0;
        (void) ret;

        metal_device_close(dev);
        ipi.registered = 0;
    }
}

static struct remoteproc * rzv2_proc_init (struct remoteproc * rproc, const struct remoteproc_ops * ops, void * arg)
{
    struct remoteproc_priv * prproc = arg;
    struct metal_device    * dev;
    int ret;

    /* Initialize MHU driver */
    g_mhu_b_ns0.p_api->open(g_mhu_b_ns0.p_ctrl, g_mhu_b_ns0.p_cfg);
    g_mhu_b_ns0.p_api->callbackSet(g_mhu_b_ns0.p_ctrl, rzv2_mhu_callback, NULL, NULL);

    if ((!rproc) || (!prproc) || (!ops))
    {
        return NULL;
    }

    rproc->priv = prproc;
    rproc->ops  = ops;

    if (!ipi.registered)
    {
        /* Get an IPI device (Mailbox) */
        ret = metal_device_open(ipi.bus_name, ipi.name, &dev);
        if (ret)
        {
            LPERROR("Failed to open ipi device: %d.\n", ret);

            return NULL;
        }

        ipi.dev = dev;
        ipi.io  = metal_device_io_region(dev, 0x0U);
        if (!ipi.io)
        {
            goto err1;
        }

#ifdef __linux__
        atomic_flag_test_and_set(&ipi.sync);
#endif
        LPRINTF("Successfully probed IPI device\n");
    }

    ret = rzv2_enable_interrupt(rproc, ipi.dev);
    if (ret)
    {
        LPERROR("Failed to register the interrupt handler.\n");
        goto err1;
    }

    ipi.registered++;

    /* Get the resource table device */
    if (init_memory_device(rproc, &prproc->vr_info->rsc))
    {
        goto err1;
    }

    /* Get VRING related devices */
    if (init_memory_device(rproc, &prproc->vr_info->ctl))
    {
        goto err1;
    }

    if (init_memory_device(rproc, &prproc->vr_info->shm))
    {
        goto err1;
    }

    return rproc;
err1:
    metal_device_close(ipi.dev);

    return NULL;
}

static void rzv2_proc_remove (struct remoteproc * rproc)
{
    if (!rproc)
    {
        return;
    }

    if (ipi.registered > 1)
    {
        ipi.registered--;

        return;
    }

    /* Disable interrupts */
    rzv2_disable_interrupt(rproc);
}

static int rzv2_proc_notify (struct remoteproc * rproc, uint32_t id)
{
    struct remoteproc_priv * prproc = rproc->priv;
    LPRINTF("rzv2_proc_notify\n");

#ifdef __linux__

    /* Put a message saying "This is the notify_id of mine!" */
    metal_io_write32_with_check(ipi.io, MBX_MSG_REG(MBX_NO), (uint64_t) prproc->notify_id);

    /* Send notification */
    metal_io_write32_with_check(ipi.io, MBX_CTRL_LOCAL_REG(MBX_NO), 0x1U);
#else
    g_mhu_b_ns0.p_api->msgSend(g_mhu_b_ns0.p_ctrl, prproc->notify_id);
#endif

    return 0;
}

#ifdef __linux__
static void * rzv2_proc_mmap (struct remoteproc       * rproc,
                              metal_phys_addr_t       * pa,
                              metal_phys_addr_t       * da,
                              size_t                    size,
                              unsigned int              attribute,
                              struct metal_io_region ** io)
{
    metal_phys_addr_t        lpa, lda;
    struct metal_io_region * tmpio;
    struct remoteproc_priv * prproc;
    (void) attribute;
    (void) size;

    if (!rproc)
    {
        return NULL;
    }

    prproc = rproc->priv;

    lpa = *pa;
    lda = *da;

    if ((lpa == METAL_BAD_PHYS) && (lda == METAL_BAD_PHYS))
    {
        return NULL;
    }

    if (lpa == METAL_BAD_PHYS)
    {
        lpa = lda;
    }

    if (lda == METAL_BAD_PHYS)
    {
        lda = lpa;
    }

    tmpio = prproc->vr_info->rsc.io;   /* We consider the resource table device only */
    if (!tmpio)
    {
        return NULL;
    }

    *pa = lpa;
    *da = lda;
    if (io)
    {
        *io = tmpio;
    }

    return metal_io_phys_to_virt(tmpio, lpa);
}

#endif

/* processor operations in rzv2. It defines
 * notification operation and remote processor managementi operations. */
struct remoteproc_ops rzv2_proc_ops =
{
    .init   = rzv2_proc_init,
    .remove = rzv2_proc_remove,
#ifdef __linux__
    .mmap     = rzv2_proc_mmap,
#else
    .mmap     = NULL,
#endif
    .notify   = rzv2_proc_notify,
    .start    = NULL,
    .stop     = NULL,
    .shutdown = NULL,
};
