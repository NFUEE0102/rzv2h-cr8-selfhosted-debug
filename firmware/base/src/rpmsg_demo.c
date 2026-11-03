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
 * @file    sample_rpmsg.c
 * @brief   rpmsg sample program for FreeRTOS
 * @date    2020.03.24
 * @author  Copyright (c) 2020, eForce Co., Ltd. All rights reserved.
 *
 ****************************************************************************
 * @par     History
 *          - rev 1.0 (2020.01.28) Imada
 *            Initial version.
 *          - rev 1.1 (2020.03.24) Imada
 *            Employed a dedicated function to set a string for Shared memory API.
 ****************************************************************************
 */
#include "FreeRTOS.h"
#include "openamp/open_amp.h"
#include "platform_info.h"
#include "rsc_table.h"

#define IPCTS_GTCNT   (*(volatile unsigned int *)0x13010648U)
extern volatile unsigned int g_ipcts_isr;
extern volatile unsigned int g_ipcts_task;
extern volatile unsigned int g_ipcts_cb;
#include "r8_pwm_proto.h"
#include "r8_blackbox.h"
#include "task.h"

extern int pwm_apply(uint32_t gpt, uint32_t use_b, uint32_t freq_hz,
                    uint32_t duty_permille, uint32_t * out_period, uint32_t * out_duty);
extern uint32_t pwm_pclk_hz(void);
extern void jitter_stats_reset(void);
extern volatile uint32_t g_jit_count, g_jit_min, g_jit_max, g_jit_sum_lo, g_jit_sum_hi;
extern volatile uint32_t g_jit_n1, g_jit_n10, g_jit_n100, g_jit_nominal;


/* Payload definition */
struct _payload {
    unsigned long num;
    unsigned long size;
    unsigned char data[];
};

/* Payload information */
struct payload_info {
    int min;
    int max;
    int num;
};

/* Globals */
static struct rpmsg_endpoint rp_ept[CFG_RPMSG_SVCNO] = {0};
static struct _payload *i_payload;
static int rnum = 0;
static int err_cnt = 0;
static char *svc_name = NULL;

/* External functions */
extern int  init_system(void);
extern void cleanup_system(void);

#define SHUTDOWN_MSG     (0xEF56A55A)

/* Local variables */

/*-----------------------------------------------------------------------------*
 *  RPMSG callbacks setup by remoteproc_resource_init()
 *-----------------------------------------------------------------------------*/

/* Local variables */



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

/* ⚠️ R8 這側絕不能用阻塞版的 rpmsg_send()。
 *
 * doc 16 鐵律②:「rpmsg_send() 拿不到 buffer 會無限阻塞」。A55 那側早就
 * 改用 rpmsg_trysend() 了,**R8 這側一直沒改**。
 *
 * 這裡特別致命,因為 endpoint callback 是在 **IpiTask(優先權 4)** 裡跑的,
 * 而且**持有 rdev->lock**。一旦阻塞:
 *   - 優先權 4 的 task 不放 CPU  -> 感測器 task(2)、main_task(1)全被餓死
 *   - rdev->lock 不釋放          -> 任何人都進不了 rpmsg
 *   - 整顆 R8 看起來像死了,但其實只是卡在這一行
 *
 * 2026-08-24 用黑盒子實測到:凍結當下 hb_eptcb=1、send_ok=0、send_err=0
 * —— callback 進去了,rpmsg_send() 就沒再出來過,而且 fault_type=0
 * (不是堆疊溢位也不是 malloc 失敗)。
 *
 * 改成 trysend + 有界重試。拿不到 buffer 就放棄這一則並記錄,
 * 因為丟一則訊息遠比整顆核心停擺好。 */
static int r8_send_reply (struct rpmsg_endpoint * ept, const void * p, int len)
{
    int ret = RPMSG_ERR_NO_BUFF;
    int i;

    for (i = 0; i < 100; i++)
    {
        ret = rpmsg_trysend(ept, (void *) p, len);
        if (RPMSG_ERR_NO_BUFF != ret)
        {
            break;
        }
        /* 讓出 CPU,讓 main_task 有機會回收 buffer。
         * 這正是阻塞版做不到的事 —— 它在優先權 4 上空轉。 */
        vTaskDelay(1);
    }

    if (ret >= 0) { R8_BB_INC(send_ok); } else { R8_BB_INC(send_err); }
    return ret;
}

static int rpmsg_endpoint_cb0 (struct rpmsg_endpoint * cb_rp_ept, void * data, size_t len, uint32_t src, void * priv)
{
#ifdef BSP_SUPPORT_CORE_CM33 //SLAVE
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
#else
    (void)cb_rp_ept;
    (void)src;
    (void)priv;
    int i;
    int ret = 0;
    struct _payload *r_payload = (struct _payload *)data;

    LPRINTF(" received payload number %lu of size %lu \r\n",
    r_payload->num, len);

    if (r_payload->size == 0) {
        LPERROR(" Invalid size of package is received.\n");
        err_cnt++;
        return -1;
    }
    /* Validate data buffer integrity. */
    for (i = 0; i < (int)r_payload->size; i++) {
        if (r_payload->data[i] != 0xA5) {
            LPRINTF("Data corruption at index %d\n", i);
            err_cnt++;
            ret = -1;
            break;
        }
    }
    rnum = r_payload->num + 1;
    return ret;
#endif
}

static int rpmsg_endpoint_cb1 (struct rpmsg_endpoint * cb_rp_ept, void * data, size_t len, uint32_t src, void * priv)
{
#ifndef BSP_SUPPORT_CORE_CM33 //SLAVE
    /* service 1 */
    (void) priv;
    (void) src;

    g_ipcts_cb = IPCTS_GTCNT;   /* T3 */

    R8_BB_INC(hb_eptcb);

    /* On reception of a shutdown we signal the application to terminate */
    if ((*(unsigned int *) data) == SHUTDOWN_MSG)
    {
        evt_svc_unbind[1] = 1;

        return RPMSG_SUCCESS;
    }

    /* Carry T1..T4 back to the CA55 in bytes 16..31 of the echoed buffer.
     * Offset 16 clears the CA55-side struct _payload header (two LP64 longs);
     * the CR8 never interprets those bytes, it echoes the buffer verbatim.
     * The CA55 must exclude this window from its 0xA5 integrity check -- see
     * patch-a55-timestamps.py, or the max-length probe reports "15 bytes". */
    if (len >= 32U)
    {
        volatile unsigned int * ts = (volatile unsigned int *)((unsigned char *) data + 16);
        ts[0] = g_ipcts_isr;
        ts[1] = g_ipcts_task;
        ts[2] = g_ipcts_cb;
        ts[3] = IPCTS_GTCNT;   /* T4: immediately before handing to rpmsg_send */
    }

    /* pwm-demo:SNSQ(感測器查詢)已移除 —— 這種封包會走最後的回聲路徑 */

    /* ---- tick 抖動查詢(v2)------------------------------------------- */
    if (len >= sizeof(jit_cmd_t))
    {
        const jit_cmd_t * jc = (const jit_cmd_t *) data;
        if (JIT_CMD_MAGIC == jc->magic)
        {
            jit_rsp_t jr;
            jr.magic   = JIT_RSP_MAGIC;
            jr.abi_ver = PWM_ABI_VER;
            if (PWM_ABI_VER != jc->abi_ver)
            {
                jr.count = 0u; jr.nominal = 0u; jr.min_d = 0u; jr.max_d = 0u;
                jr.sum_lo = 0u; jr.sum_hi = 0u;
                jr.n_1us = 0u; jr.n_10us = 0u; jr.n_100us = 0u;
                jr.pclk_hz = 0u;
            }
            else
            {
                /* 一次快照。tick hook 仍在跑,所以各欄位未必嚴格同一瞬間 ——
                 * 對 10^5 量級的樣本數而言誤差可忽略,但要誠實標註。 */
                jr.count   = g_jit_count;
                jr.nominal = g_jit_nominal;
                jr.min_d   = g_jit_min;
                jr.max_d   = g_jit_max;
                jr.sum_lo  = g_jit_sum_lo;
                jr.sum_hi  = g_jit_sum_hi;
                jr.n_1us   = g_jit_n1;
                jr.n_10us  = g_jit_n10;
                jr.n_100us = g_jit_n100;
                jr.pclk_hz = pwm_pclk_hz();
                if (0u != jc->reset) { jitter_stats_reset(); }
            }
            (void) r8_send_reply(cb_rp_ept, &jr, (int) sizeof(jr));
            return RPMSG_SUCCESS;
        }
    }

    /* ---- A55 -> R8 PWM 控制(2026-08-13,doc 16 §5.6)--------------------
     * 靠 magic 辨識;不是命令的封包一律照舊回聲,所以 r8_bench 與原廠 client
     * 完全不受影響。r8_bench 的第一個欄位是遞增的 round index,不可能撞到 magic。 */
    if (len >= sizeof(pwm_cmd_t))
    {
        const pwm_cmd_t * c = (const pwm_cmd_t *) data;
        if (PWM_CMD_MAGIC == c->magic)
        {
            pwm_rsp_t r;
            r.magic         = PWM_RSP_MAGIC;
            r.abi_ver       = PWM_ABI_VER;
            r.period_counts = 0u;
            r.duty_counts   = 0u;
            r.pclk_hz       = pwm_pclk_hz();
            r.status        = (PWM_ABI_VER != c->abi_ver)
                            ? PWM_ERR_ABI
                            : pwm_apply(c->gpt, c->use_b, c->freq_hz, c->duty_permille,
                                        &r.period_counts, &r.duty_counts);
            (void) r8_send_reply(cb_rp_ept, &r, (int) sizeof(r));
            return RPMSG_SUCCESS;
        }
    }

    /* Send data back to master */
    if (rpmsg_send(cb_rp_ept, data, (int) len) < 0)
    {
        LPERROR("rpmsg_send failed\n");

        return -1;
    }

    return RPMSG_SUCCESS;
#else
    (void)cb_rp_ept;
    (void)src;
    (void)priv;
    int i;
    int ret = 0;
    struct _payload *r_payload = (struct _payload *)data;

    LPRINTF(" received payload number %lu of size %lu \r\n",
    r_payload->num, len);

    if (r_payload->size == 0) {
        LPERROR(" Invalid size of package is received.\n");
        err_cnt++;
        return -1;
    }
    /* Validate data buffer integrity. */
    for (i = 0; i < (int)r_payload->size; i++) {
        if (r_payload->data[i] != 0xA5) {
            LPRINTF("Data corruption at index %d\n", i);
            err_cnt++;
            ret = -1;
            break;
        }
    }
    rnum = r_payload->num + 1;
    return ret;
#endif
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

void rpmsg_service_bind(struct rpmsg_device *rdev, const char *name, uint32_t dest)
{
    LPRINTF("new endpoint notification is received.\n");
    if (strcmp(name, svc_name)) {
        LPERROR("Unexpected name service %s.\n", name);
    }
    else
        (void)rpmsg_create_ept(&rp_ept[1], rdev, svc_name,
                       APP_EPT_ADDR, dest,
                       rpmsg_endpoint_cb1,
                       rpmsg_service_unbind1);
    return ;
}

static int payload_init(struct rpmsg_device *rdev, struct payload_info *pi) {
    int rpmsg_buf_size = 0;

    /* Get the maximum buffer size of a rpmsg packet */
    if ((rpmsg_buf_size = rpmsg_virtio_get_buffer_size(rdev)) <= 0) {
        return rpmsg_buf_size;
    }

    pi->min = 1;
    pi->max = rpmsg_buf_size - 24;
    pi->num = pi->max / pi->min;

    i_payload =
        (struct _payload *)metal_allocate_memory(2 * sizeof(unsigned long) +
                      pi->max);
    if (!i_payload) {
        LPERROR("memory allocation failed.\n");
        return -ENOMEM;
    }

    return 0;
}

/*-----------------------------------------------------------------------------*
 *  Application
 *-----------------------------------------------------------------------------*/
int app (struct rpmsg_device * rdev, void * platform, unsigned long svcno)
{
    //(void) platform;
    int ret;
    int shutdown_msg = SHUTDOWN_MSG;
    int i;
    int size;
    int expect_rnum = 0;
    struct payload_info pi = { 0 };

#ifdef BSP_SUPPORT_CORE_CM33
    if (svcno == 1UL)
    {
//      LPRINTF(" 1 - Send data to remote core, retrieve the echo");
//      LPRINTF(" and validate its integrity ..\n");

        /* Initialization of the payload and its related information */
        if ((ret = payload_init(rdev, &pi))) {
            return ret;
        }
    }
#endif
    if (svcno == 0UL)
    {
        svc_name =  CFG_RPMSG_SVC_NAME0;
        ret = rpmsg_create_ept(&rp_ept[0],
                               rdev,
                               svc_name,
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
        svc_name =  CFG_RPMSG_SVC_NAME1;
        ret = rpmsg_create_ept(&rp_ept[1],
                               rdev,
                               svc_name,
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

#ifdef BSP_SUPPORT_CORE_CM33
    if (svcno == 0UL)
#else
    if (svcno != 0UL)
#endif
    {
    LPRINTF("Waiting for events...\n");
    while (1)
    {
            vTaskDelay(10);

        /* we got a shutdown request, exit */
        if (evt_svc_unbind[svcno])
        {
            break;
        }
    }

    /* Clear shutdown flag */
    evt_svc_unbind[svcno] = 0;
    }
    else
    {
        while (!is_rpmsg_ept_ready(&rp_ept[1]))
             platform_poll(platform);

        LPRINTF("RPMSG service has created.\n");
        for (i = 0, size = pi.min; i < (int)pi.num; i++, size++) {
            i_payload->num = i;
            i_payload->size = size;

            /* Mark the data buffer. */
            memset(&(i_payload->data[0]), 0xA5, size);

            LPRINTF("sending payload number %lu of size %lu\n",
                 i_payload->num, (2 * sizeof(unsigned long)) + size);

            ret = rpmsg_send(&rp_ept[1], i_payload,
                 (2 * sizeof(unsigned long)) + size);

            if (ret < 0) {
                LPRINTF("Error sending data...%d\n", ret);
            break;
            }
            LPRINTF("echo test: sent : %lu\n", (2 * sizeof(unsigned long)) + size);

            expect_rnum++;
            do {
                platform_poll(platform);
            } while ((rnum < expect_rnum) && !err_cnt);
            vTaskDelay(10);
        }

        LPRINTF("************************************\n");
        LPRINTF(" Test Results: Error count = %d \n", err_cnt);
        LPRINTF("************************************\n");
        /* Send shutdown message to remote */
        rpmsg_send(&rp_ept[1], &shutdown_msg, sizeof(int));
        vTaskDelay(1);
        LPRINTF("Quitting application .. Echo test end\n");

        metal_free_memory(i_payload);
    }
    return 0;
}
