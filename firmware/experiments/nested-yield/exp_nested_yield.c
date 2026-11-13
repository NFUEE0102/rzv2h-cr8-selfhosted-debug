/*
 * Experiment: what happens when a *nested* interrupt asks for a context switch?
 *
 * Two probes, both in application code:
 *   exp_irq_exit_hook()       end of every interrupt (from r8_irq_guard(): after the handler
 *                             body, IRQs masked, just before control returns to IRQ_Handler)
 *   exp_nested_yield_probe()  in the rpmsg notification task (metal_ipi_task), right after it
 *                             has been woken by the MHU doorbell ISR
 *
 * Results are mirrored into a block of words in the unused part of the black-box window
 * (black box base + 0x800), so they can be read from Linux with devmem:
 *   w0   magic 0x31505845 ("EXP1")
 *   w1   nested interrupts that end with ulPortYieldRequired set (an outer ISR is in progress)
 *   w2   ... of those, the outer ISR found the flag still set at its own end
 *   w3   ... of those, the outer ISR found the flag clear (the inner exit took the switch path)
 *   w4   last such pair: inner GIC INTID << 16 | outer vector number
 *   w5   GICC_RPR at the inner exit
 *   w6   first four characters of the name of the interrupted task (last event)
 *   w7   events where the scheduler was not in the RUNNING state at the inner exit
 *   w8   wake-ups of the notification task between the inner exit and the end of the outer ISR
 *   w9   wake-ups of the notification task after the outer ISR had ended
 *   w10  wake-ups with g_current_interrupt_pointer != 0 (BSP count of ISRs in progress)
 *   w11  (0x100 | RPR) << 16 for the last normal wake-up, (0x100 | RPR) for the last bad one
 *   w12  bad wake-ups:    samples << 16 | sum of tick-count advances over 3 tick-timer periods
 *   w13  normal wake-ups: samples << 16 | sum of tick-count advances over 3 tick-timer periods
 *   w14..w16  tick-timer counter at the inner exit / at the wake-up / at the end of the outer ISR
 *   w17  tick-timer period register
 *   w18  progress counter of the background task (workload 1) / control task (workload 2)
 *   w19  progress counter of the housekeeping task (workload 2)
 *
 * The firmware is otherwise idle between messages, and the idle hook of the FSP port keeps the
 * scheduler suspended around its WFI (vTaskSuspendAll / xTaskResumeAll), so an interrupt taken
 * from the idle task cannot switch tasks whatever the handler does. To have an ordinary task
 * being interrupted, the probe starts a workload, chosen by EXP_WORKLOAD in exp_config.h:
 *   0  none
 *   1  one background task at tskIDLE_PRIORITY that always computes (variant exp-nested-yield)
 *   2  an ordinary application: a 100 Hz control task and a housekeeping task, CPU mostly idle
 *      (variant exp-normal-app)
 */
#include "bsp_api.h"
#include "FreeRTOS.h"
#include "task.h"
#include "r8_blackbox.h"
#include "exp_config.h"   /* EXP_WORKLOAD, written by apply.py */

#define EXP_TICK_TIMER    (R_GTM5)     /* the tick timer of this core (core1: GTM channel 5) */
#if (EXP_WORKLOAD == 2)
 #define EXP_SAMPLES      (0u)       /* the ordinary application is not disturbed by the tick sampling */
#else
 #define EXP_SAMPLES      (8u)
#endif
#define EXP_SPIN_LIMIT    (8000000u)   /* gives up if the timer is not running */
#define EXP_W(i)          (((volatile uint32_t *) ((uintptr_t) R8_BB + 0x800u))[(i)])

extern uint8_t           g_current_interrupt_pointer;
extern uint16_t          g_current_interrupt_num[];
extern volatile uint32_t ulPortYieldRequired;

void exp_irq_exit_hook(uint32_t icciar);
void exp_nested_yield_probe(void);

/* 0: idle, 1: a nested interrupt left with a yield request, outer ISR not finished yet,
 * 2: that outer ISR has finished, the notification task has not run since */
static volatile uint32_t s_stage;

void exp_irq_exit_hook (uint32_t icciar)
{
    if (0u != g_current_interrupt_pointer)
    {
        if (0u != ulPortYieldRequired)
        {
            const char * name = pcTaskGetName(NULL);

            s_stage = 1u;
            EXP_W(0) = 0x31505845u;
            EXP_W(1)++;
            EXP_W(4)  = ((icciar & 0x3FFu) << 16) | g_current_interrupt_num[0];
            EXP_W(5)  = R_INTC_GIC->GICC_ICCRPR & 0xFFu;
            EXP_W(6)  = ((uint32_t) name[0]) | ((uint32_t) name[1] << 8) | ((uint32_t) name[2] << 16) |
                        ((uint32_t) name[3] << 24);
            EXP_W(14) = EXP_TICK_TIMER->OSTMnCNT;
            EXP_W(17) = EXP_TICK_TIMER->OSTMnCMP;
            if (taskSCHEDULER_RUNNING != xTaskGetSchedulerState())
            {
                EXP_W(7)++;
            }
        }
    }
    else if (1u == s_stage)
    {
        s_stage   = 2u;
        EXP_W(16) = EXP_TICK_TIMER->OSTMnCNT;
        if (0u != ulPortYieldRequired)
        {
            EXP_W(2)++;
        }
        else
        {
            EXP_W(3)++;
        }
    }
    else
    {
        /* not after a nested yield */
    }
}

/* CPU-bound work: about 0.5 ms per 100000 iterations on the RZ/V2H CR8 */
static uint32_t exp_compute (uint32_t iterations)
{
    static uint32_t x = 0x12345678u;

    for (uint32_t i = 0u; i < iterations; i++)
    {
        x = (x * 1664525u) + 1013904223u;
    }

    return x;
}

#if (EXP_WORKLOAD == 1)

/* Workload 1: one background task at tskIDLE_PRIORITY that always computes. */
static void exp_busy_task (void * arg)
{
    (void) arg;
    for ( ; ; )
    {
        EXP_W(18) += 1u + (exp_compute(100000u) & 0u);
    }
}

static void exp_start_workload (void)
{
    (void) xTaskCreate(exp_busy_task, "exp_busy", 256u, NULL, tskIDLE_PRIORITY, NULL);
}

#elif (EXP_WORKLOAD == 2)

/* Workload 2: an ordinary application. A 100 Hz control task (about 1 ms of work per period)
 * and a housekeeping task (about 3 ms of work, then 7 ms asleep): the CPU is idle more than half
 * of the time. */
static void exp_ctrl_task (void * arg)
{
    TickType_t last = xTaskGetTickCount();

    (void) arg;
    for ( ; ; )
    {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(10));
        EXP_W(18) += 1u + (exp_compute(200000u) & 0u);
    }
}

static void exp_housekeeping_task (void * arg)
{
    (void) arg;
    for ( ; ; )
    {
        EXP_W(19) += 1u + (exp_compute(600000u) & 0u);
        vTaskDelay(pdMS_TO_TICKS(7));
    }
}

static void exp_start_workload (void)
{
    (void) xTaskCreate(exp_ctrl_task, "exp_ctrl", 256u, NULL, tskIDLE_PRIORITY + 3, NULL);
    (void) xTaskCreate(exp_housekeeping_task, "exp_hk", 256u, NULL, tskIDLE_PRIORITY + 1, NULL);
}

#else

static void exp_start_workload (void)
{
}

#endif

/* Busy-waits until the tick timer has wrapped three times and returns how many ticks FreeRTOS
 * counted meanwhile. */
static uint32_t exp_ticks_over_3_periods (void)
{
    uint32_t cmp   = EXP_TICK_TIMER->OSTMnCMP;
    uint32_t t0    = (uint32_t) xTaskGetTickCount();
    uint32_t prev  = EXP_TICK_TIMER->OSTMnCNT;
    uint32_t wraps = 0u;
    uint32_t spin  = 0u;

    while ((wraps < 3u) && (spin < EXP_SPIN_LIMIT))
    {
        uint32_t cur = EXP_TICK_TIMER->OSTMnCNT;
        uint32_t d   = (cur > prev) ? (cur - prev) : (prev - cur);
        if (d > (cmp / 2u))
        {
            wraps++;
        }

        prev = cur;
        spin++;
    }

    return (uint32_t) xTaskGetTickCount() - t0;
}

void exp_nested_yield_probe (void)
{
    static uint32_t wakeups;
    static uint32_t n_bad;
    static uint32_t n_norm;
    static uint32_t sum_bad;
    static uint32_t sum_norm;

    static uint32_t started;
    if (0u == started)
    {
        started = 1u;
        exp_start_workload();
    }

    uint32_t depth = g_current_interrupt_pointer;
    uint32_t rpr   = R_INTC_GIC->GICC_ICCRPR & 0xFFu;
    uint32_t stage = s_stage;

    if (1u == stage)
    {
        EXP_W(8)++;
        EXP_W(15) = EXP_TICK_TIMER->OSTMnCNT;
    }
    else if (2u == stage)
    {
        s_stage = 0u;
        EXP_W(9)++;
        EXP_W(15) = EXP_TICK_TIMER->OSTMnCNT;
    }
    else
    {
        /* an ordinary wake-up */
    }

    wakeups++;
    if (0u != depth)
    {
        EXP_W(10)++;
        EXP_W(11) = (EXP_W(11) & 0xFFFF0000u) | 0x100u | rpr;
        if (n_bad < EXP_SAMPLES)
        {
            sum_bad += exp_ticks_over_3_periods();
            n_bad++;
            EXP_W(12) = (n_bad << 16) | (sum_bad & 0xFFFFu);
        }
    }
    else
    {
        EXP_W(11) = (EXP_W(11) & 0x0000FFFFu) | ((0x100u | rpr) << 16);
        if ((n_norm < EXP_SAMPLES) && (0x200u == (wakeups & 0x7FFu)))
        {
            sum_norm += exp_ticks_over_3_periods();
            n_norm++;
            EXP_W(13) = (n_norm << 16) | (sum_norm & 0xFFFFu);
        }
    }
}
