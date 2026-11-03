/*
 * R8 PWM 腳位探索版(v4,2026-08-13)
 *
 * 目的:查出 J1 上身分不明的 10 支腳(pin 3/5/12/27/28/29/33/35/38/40)實際接哪個 SoC 腳。
 *
 * 背景:v3 的 13 路實測後發現 doc 04 的 J1 腳位表至少 5 列是錯的 ——
 *   P51/P52/P53 排列錯位(實際在 J1-36/37/31,表上寫 31/33/36)
 *   P84/P85 掃遍 15 支腳都沒出現,根本不在那些位置
 * 所以剩下的腳位不能再信表,只能實測。
 *
 * 方法:每支未定位的腳給一個獨特脈寬,人工掃過那 10 支腳,讀數即身分。
 *
 *   1000us P76 (GPT6.A)    1200us P95 (GPT4.B)    1400us PA7 (GPT7.B)
 *   1050us P77 (GPT6.B)    1250us P96 (GPT9.A)    1450us P70 (GPT0.A) ← 錨點 J1-15
 *   1100us P84 (GPT5.A)    1300us P97 (GPT9.B)    1500us P50 (GPT8.A) ← 錨點 J1-22
 *   1150us P85 (GPT5.B)    1350us PA6 (GPT7.A)
 *
 * ⚠ 本版暫時讓出 PA4(J1-32)與 P75(J1-7):P76 只能走 GPT6.A、P95 只能走 GPT4.B,
 *   都與它們衝突。兩者都已實體確認過,可安全犧牲 —— 所以這一版 J1-32 和 J1-7 會是暗的。
 *
 * 兩個錨點的用途:若整排都沒訊號,錨點能立刻分辨是「韌體沒跑」還是「這些腳真的沒接」。
 */
#include "hal_data.h"
#include "r8_blackbox.h"
#include "r8_pwm_proto.h"
#include "common_data.h"   /* g_ioport_ctrl */
#include "FreeRTOS.h"
#include "FreeRTOS.h"
#include "task.h"

#define LED_PIN         BSP_IO_PORT_11_PIN_05
#define GPT_CLK_HZ      200000000u
#define SERVO_HZ        50u
#define PERIOD_COUNTS   (GPT_CLK_HZ / SERVO_HZ)      /* 4,000,000 = 20 ms */

typedef struct
{
    timer_ctrl_t      * ctrl;
    timer_cfg_t const * cfg;
    uint8_t             has_a;
    uint8_t             has_b;
    uint32_t            us_a;
    uint32_t            us_b;
} pwm_group_t;

static const pwm_group_t g_groups[] = {
    { (timer_ctrl_t *) &g_gpt0_ctrl, &g_gpt0_cfg, 1, 0, 1450u,    0u },  /* P70 錨點 */
    { (timer_ctrl_t *) &g_gpt4_ctrl, &g_gpt4_cfg, 0, 1,    0u, 1200u },  /* P95 */
    { (timer_ctrl_t *) &g_gpt5_ctrl, &g_gpt5_cfg, 1, 1, 1100u, 1150u },  /* P84 / P85 */
    { (timer_ctrl_t *) &g_gpt6_ctrl, &g_gpt6_cfg, 1, 1, 1000u, 1050u },  /* P76 / P77 */
    { (timer_ctrl_t *) &g_gpt7_ctrl, &g_gpt7_cfg, 1, 1, 1350u, 1400u },  /* PA6 / PA7 */
    { (timer_ctrl_t *) &g_gpt8_ctrl, &g_gpt8_cfg, 1, 0, 1500u,    0u },  /* P50 錨點 */
    { (timer_ctrl_t *) &g_gpt9_ctrl, &g_gpt9_cfg, 1, 1, 1250u, 1300u },  /* P96 / P97 */
};
#define N_GROUP  (sizeof(g_groups) / sizeof(g_groups[0]))

/* ===== A55 -> R8 PWM 控制(2026-08-13,doc 16 §5.6)=========================
 * GPT 的來源時脈。doc 15 §5 掃頻掃到輸出上限 100 MHz = PCLK/2 ⇒ PCLK = 200 MHz;
 * 現行 50 Hz 設定的 GTPR = 0x003D08FF = 3,999,999 也吻合(4e6 counts = 20 ms)。 */
#define PWM_PCLK_HZ   200000000u

/* g_groups[] 的排列由本檔上方的陣列決定,對外用 GPT 編號比較直覺
 * (使用者查的是 doc 15 §7.2 那張 GPT->J1 腳位表)。 */
static int pwm_group_of_gpt (uint32_t gpt)
{
    switch (gpt)
    {
        case 0: return 0;
        case 4: return 1;
        case 5: return 2;
        case 6: return 3;
        case 7: return 4;
        case 8: return 5;
        case 9: return 6;
        default: return -1;
    }
}

int pwm_apply (uint32_t gpt, uint32_t use_b, uint32_t freq_hz, uint32_t duty_permille,
               uint32_t * out_period, uint32_t * out_duty)
{
    int gi = pwm_group_of_gpt(gpt);
    if (gi < 0)                  return PWM_ERR_BAD_GPT;
    if (0u == freq_hz)           return PWM_ERR_ZERO_FREQ;
    if (duty_permille > 1000u)   return PWM_ERR_BAD_DUTY;

    pwm_group_t const * g = &g_groups[gi];
    if (use_b ? (0u == g->has_b) : (0u == g->has_a))
    {
        return PWM_ERR_NO_SUCH_PIN;
    }

    uint64_t period64 = (uint64_t) PWM_PCLK_HZ / (uint64_t) freq_hz;
    if ((period64 < 2u) || (period64 > 0xFFFFFFFFu))
    {
        return PWM_ERR_RANGE;
    }
    uint32_t period = (uint32_t) period64;
    uint32_t duty   = (uint32_t) (((uint64_t) period * (uint64_t) duty_permille) / 1000u);

    /* ⚠️ 順序不能換(doc 15 §「改頻率必須先停 GPT」):
     *   R_GPT_DutyCycleSet 是拿**當下的 GTPR** 檢查範圍,
     *   而 R_GPT_PeriodSet 在運轉中只寫緩衝暫存器 GTPBR(GTPR 要到下個週期邊界才更新)。
     * 所以運轉中「先設 duty 再設 period」,只要新 duty 超過**舊**週期就會被歸零 ——
     * 輸出整段停在低電位,而且暫存器看起來全部正常。
     * 停下來設則 R_GPT_PeriodSet 會直接寫 GTPR,duty 檢查就用得到新週期。
     * 代價是換設定時有一次極短的輸出中斷。 */
    if (FSP_SUCCESS != R_GPT_Stop(g->ctrl))                     return PWM_ERR_STOP;
    if (FSP_SUCCESS != R_GPT_PeriodSet(g->ctrl, period))        return PWM_ERR_PERIOD;
    if (FSP_SUCCESS != R_GPT_DutyCycleSet(g->ctrl, duty,
                            use_b ? GPT_IO_PIN_GTIOCB : GPT_IO_PIN_GTIOCA))
    {
        return PWM_ERR_DUTY;
    }
    if (FSP_SUCCESS != R_GPT_Start(g->ctrl))                    return PWM_ERR_START;

    if (NULL != out_period) { *out_period = period; }
    if (NULL != out_duty)   { *out_duty   = duty;   }
    return 0;
}

uint32_t pwm_pclk_hz (void) { return PWM_PCLK_HZ; }

/* ===== tick 抖動探針(2026-08-13,doc 16 §5.7)==============================
 * 在 FreeRTOS tick ISR(configTICK_RATE_HZ = 1 kHz)裡:
 *   1. 讀 GPT0 GTCNT(5 ns/count)算與上一個 tick 的間隔,累積統計
 *      (pwm-demo:時基從 GPT6 改 GPT0 —— GPT6 是網頁示範的主輸出通道;
 *       對 GPT0 下 PWMC 改頻率一樣會毀掉統計,查抖動前別動 GPT0)
 *   2. 翻轉 P97(J1 pin 40)-> 500 Hz 方波,供示波器獨立交叉驗證
 *
 * ⚠️ GTCNT 在 GTPR+1 處歸零(不是 2^32),所以差值要對 GTPR+1 取模。
 *    GPT6 現行 GTPR+1 = 4,000,000 counts = 20 ms,而 tick 是 1 ms,
 *    每 20 個 tick 會遇到一次歸零 —— 不處理的話那次會算出巨大的假間隔。
 *
 * 量的是 **ISR 層級**抖動:這是地板值。週期性 *task* 還要再加排程器那一份。 */
#define JIT_GTCNT     (*(volatile unsigned int *)0x13010048U)   /* GPT0 GTCNT */
#define JIT_GTPR      (*(volatile unsigned int *)0x13010064U)   /* GPT0 GTPR  */
#define JIT_PIN       ((bsp_io_port_pin_t) BSP_IO_PORT_09_PIN_07)  /* P97 = J1 pin 40 */

/* 抖動探針要不要接管 P97 當方波輸出。
 * 0 = 只累積統計(正式韌體用):PWM 照常從 GTIOC9B 出來,pin 40 不受影響。
 * 1 = 接管 P97 翻成 500 Hz 方波(量測韌體 cr8_jitter.elf 用),供示波器交叉驗證,
 *     代價是 **pin 40 上的 PWM 會停**。
 * 統計本身兩種都有,所以正式韌體隨時可以用 `r8_bench_pwm jitter` 查。 */
#ifndef JIT_PIN_TOGGLE
 #define JIT_PIN_TOGGLE  0
#endif

volatile uint32_t g_jit_count   = 0u;
volatile uint32_t g_jit_min     = 0xFFFFFFFFu;
volatile uint32_t g_jit_max     = 0u;
volatile uint32_t g_jit_sum_lo  = 0u;
volatile uint32_t g_jit_sum_hi  = 0u;
volatile uint32_t g_jit_n1      = 0u;   /* |d - nominal| > 1 us   (200 counts) */
volatile uint32_t g_jit_n10     = 0u;   /* > 10 us  (2000 counts) */
volatile uint32_t g_jit_n100    = 0u;   /* > 100 us (20000 counts) */
volatile uint32_t g_jit_nominal = 200000u;  /* 200 MHz / 1 kHz */
static   uint32_t g_jit_prev    = 0u;
static   uint32_t g_jit_wrap    = 4000000u;
static   uint32_t g_jit_armed   = 0u;
static   uint32_t g_jit_toggle  = 0u;

void jitter_stats_reset (void)
{
    g_jit_armed  = 0u;              /* 先解除,避免半更新的統計被讀走 */
    g_jit_count  = 0u;
    g_jit_min    = 0xFFFFFFFFu;
    g_jit_max    = 0u;
    g_jit_sum_lo = 0u;
    g_jit_sum_hi = 0u;
    g_jit_n1     = 0u;
    g_jit_n10    = 0u;
    g_jit_n100   = 0u;
    g_jit_prev   = 0u;
    g_jit_armed  = 1u;
}

void jitter_probe_init (void)
{
#if JIT_PIN_TOGGLE
    /* 把 P97 從 GTIOC9B 收回來當 GPIO 輸出。GPT9 內部照跑,只是比較輸出
     * 不再送到接腳;順手停掉它免得日後看暫存器時誤會。 */
    (void) R_GPT_Stop(&g_gpt9_ctrl);
    (void) R_IOPORT_PinCfg(&g_ioport_ctrl, JIT_PIN,
                           (uint32_t) IOPORT_CFG_PORT_DIRECTION_OUTPUT | (uint32_t) IOPORT_CFG_DRIVE_B01);
#endif

    g_jit_wrap    = JIT_GTPR + 1u;                    /* 由硬體讀,不寫死 */
    g_jit_nominal = PWM_PCLK_HZ / configTICK_RATE_HZ;
    jitter_stats_reset();
}

void r8_tick_probe (void)
{
    uint32_t now;

    /* tick 心跳。這是**唯一不經過 sensor task** 的存活訊號 ——
     * uptime_ticks / hb_sensor 都是 sensor task 自己搬進黑盒子的,
     * 它一凍住那些就跟著停,分不出「tick 死了」還是「task 卡住」。
     * (2026-08-25:實體移動羅盤後 sensor task 凍住,就是卡在這個盲點。) */
    R8_BB_INC(tick_count);
    /* FreeRTOS 自己的 tick。與 tick_count 分開才分得出
     * 「ISR 在跑」與「排程器在跑」。 */
    R8_BB_SET(tick_rtos, (uint32_t) xTaskGetTickCountFromISR());

    /* ⚠️ GTCNT 讀取必須在 armed 護欄之內(2026-08-27,§11 根因)。
     * 原本第一行就讀 JIT_GTCNT —— 排程器一啟動 tick 就開跑,若第一個 tick
     * 搶在 jitter init(R_GPT_Open 開 GPT9 clock)之前,就是讀一個
     * clock-gated 的週邊暫存器 → bus error → async abort。
     * 這正是「冷開機後第一次啟動特別容易 abort」的真相:炸掉那輪的
     * GPT open 往往已跑完、clock 殘留開著,重試就贏了竞态。
     * EVK 冷開機時序稍異,tick 每次搶先 → 100% 必現,因而定位。 */
    if (0u != g_jit_armed)
    {
        now = JIT_GTCNT;
        if (0u != g_jit_prev)
        {
            uint32_t d = (now >= g_jit_prev)
                       ? (now - g_jit_prev)
                       : (g_jit_wrap - g_jit_prev + now);   /* GTPR+1 取模 */
            uint32_t nom = g_jit_nominal;
            uint32_t dev = (d > nom) ? (d - nom) : (nom - d);

            if (d < g_jit_min) { g_jit_min = d; }
            if (d > g_jit_max) { g_jit_max = d; }

            {   /* 64-bit 累加,拆成兩個 32 —— R8 上避免 64-bit RMW */
                uint32_t lo = g_jit_sum_lo + d;
                if (lo < g_jit_sum_lo) { g_jit_sum_hi++; }
                g_jit_sum_lo = lo;
            }

            if (dev > 200u)   { g_jit_n1++;   }   /* > 1 us   */
            if (dev > 2000u)  { g_jit_n10++;  }   /* > 10 us  */
            if (dev > 20000u) { g_jit_n100++; }   /* > 100 us */

            g_jit_count++;
        }
        g_jit_prev = now;
    }

#if JIT_PIN_TOGGLE
    /* 示波器交叉驗證用:1 kHz tick 翻轉 -> 500 Hz 方波 */
    g_jit_toggle ^= 1u;
    R_BSP_PinWrite(JIT_PIN, (0u != g_jit_toggle) ? BSP_IO_LEVEL_HIGH : BSP_IO_LEVEL_LOW);
#endif
}



volatile uint32_t g_open_errors = 0;
volatile uint32_t g_started     = 0;

static uint32_t duty_for_us (uint32_t pulse_us)
{
    return (PERIOD_COUNTS / 20000u) * pulse_us;
}

static void delay_ms (uint32_t ms)
{
    while (ms >= 100u)
    {
        R_BSP_SoftwareDelay(100, BSP_DELAY_UNITS_MILLISECONDS);
        ms -= 100u;
    }
    if (ms > 0u)
    {
        R_BSP_SoftwareDelay(ms, BSP_DELAY_UNITS_MILLISECONDS);
    }
}

void pwm_test_entry (void)
{
    /* 單一通道失敗不中止其餘 —— 這樣才能從暫存器看出哪幾路成功 */
    for (uint32_t i = 0; i < N_GROUP; i++)
    {
        pwm_group_t const * g = &g_groups[i];
        if (FSP_SUCCESS != R_GPT_Open(g->ctrl, g->cfg))
        {
            g_open_errors++;
            continue;
        }
        (void) R_GPT_Start(g->ctrl);
        /* pwm-demo:開機一律靜默(duty=0),等 A55 網頁下第一筆 PWMC 才有輸出。
         * 沿用 pwm_emergency_stop() 的寫法,兩個比較輸出都清零。 */
        (void) R_GPT_DutyCycleSet(g->ctrl, 0u, GPT_IO_PIN_GTIOCA);
        (void) R_GPT_DutyCycleSet(g->ctrl, 0u, GPT_IO_PIN_GTIOCB);
        g_started++;
    }

    jitter_probe_init();   /* 接管 P97,開始量 tick 抖動 */

    /* LED 心跳 + 黑盒子搬運。pump 原本由 sensor task 呼叫(2 Hz 這裡也夠,
     * pump 內部的 stack scan 自帶 1 Hz 節流)—— 漏掉它黑盒子大半欄位會凍結。 */
    {
        extern void r8_blackbox_pump(void);
        uint32_t led = 0;
        for ( ; ; )
        {
            r8_blackbox_pump();
            led ^= 1u;
            R_BSP_PinWrite((bsp_io_port_pin_t) LED_PIN,
                           led ? BSP_IO_LEVEL_HIGH : BSP_IO_LEVEL_LOW);
            /* Must yield: R_BSP_SoftwareDelay() is a busy spin that never enters
             * the scheduler, so this loop starves main_task_entry (the rpmsg
             * task) outright.  That is the real reason rpmsg never comes up
             * under cr8_disc.elf and /dev/uio* stays empty -- it is not that
             * "the client has not been started yet". */
            vTaskDelay(pdMS_TO_TICKS(500));
        }
    }
}

/* 緊急停止所有 PWM 輸出。
 *
 * 任何 fault 的第一件事都要做這個 —— GPT 是硬體驅動的,R8 死了它還會用
 * 最後的佔空比一直輸出(doc 15 §6.1 實測過:停掉 R8 不會停掉 GPT)。
 *
 * Renesas 官方的 rzv2h_drone_px4 也是同一個順序,而且註解寫得很清楚:
 *   "Emergency-disarm motors BEFORE disabling interrupts — PWM timers are
 *    hardware-driven and keep spinning at the last duty cycle if not reset."
 *
 * 由 src/r8_blackbox.c 的 fault hook 以 weak 參照呼叫。 */
void pwm_emergency_stop(void);
void pwm_emergency_stop (void)
{
    for (uint32_t i = 0; i < N_GROUP; i++)
    {
        pwm_group_t const * g = &g_groups[i];
        (void) R_GPT_DutyCycleSet(g->ctrl, 0u, GPT_IO_PIN_GTIOCA);
        (void) R_GPT_DutyCycleSet(g->ctrl, 0u, GPT_IO_PIN_GTIOCB);
        (void) R_GPT_Stop(g->ctrl);
    }
}
