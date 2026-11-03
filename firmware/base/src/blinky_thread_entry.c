#include "blinky_thread.h"
#include "r8_blackbox.h"

/* PWM 測試(src/pwm_test.c)—— 不回傳 */
extern void pwm_test_entry(void);


/*
 * 原本的 blinky 改成:先閃三次 LED 表示「韌體起來了」,再進 PWM 測試。
 *
 * 保留 LED 的用意是給一個與 PWM 無關的存活指示 —— 若 LED 有閃但 J1 pin 32
 * 量不到訊號,問題就鎖定在 GPT/腳位;若連 LED 都不閃,那是韌體根本沒跑起來。
 * 兩個獨立指示可以把故障範圍切一半。
 */
void blinky_thread_entry (__attribute__((unused)) void * pvParameters)
{
    R8_BB_STAGE(10);
    for (int i = 0; i < 6; i++)
    {
        R_BSP_PinWrite((bsp_io_port_pin_t) BSP_IO_PORT_11_PIN_05,
                       (i & 1) ? BSP_IO_LEVEL_LOW : BSP_IO_LEVEL_HIGH);
        vTaskDelay(configTICK_RATE_HZ / 5);
    }

    R8_BB_STAGE(11);
    /* pwm-demo:無感測器 —— 純 PWM 通訊示範,stage 11 保留給時序對照 */

    R8_BB_STAGE(12);
    pwm_test_entry();      /* 之後就在裡面無限迴圈輪換脈寬 */
}
