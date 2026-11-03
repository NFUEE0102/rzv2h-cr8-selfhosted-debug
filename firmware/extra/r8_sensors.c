/*
 * R8 端的 GPS 與羅盤讀取(2026-08-24)
 *
 *   GPS  : u-blox M8N,UBX 二進位,230400 8N1,RSCI5 = J1 pin 8/10 (P72/P73)
 *   羅盤 : IST8310,I2C 100 kHz,位址 0x0E,RSCI7 = J1 pin 3/5 (P76/P77)
 *
 * == 為什麼是 IST8310 而不是模組上印的 HMC5883L ==
 * 2026-08-24 在 Linux 端實測:WHO_AM_I(reg 0x00)= 0x10,那是 IST8310 的
 * 固定 ID。同時反證了另外兩顆:QMC5883L 的 ID 暫存器(0x0D)該讀到 0xFF,
 * 實測 0x00;HMC5883L 的 0x0A/0x0B/0x0C 該是 'H','4','3',實測 00/0c/00。
 * 三顆的暫存器圖完全不同,拿 HMC 的驅動來打會一個字都讀不出來。
 * 本檔的初始化序列與 Linux 端 ist8310.py 逐條對應 —— 那支已經量到
 * 穩定的地磁讀數,所以這裡照抄的是**驗證過的**序列,不是照 datasheet 猜的。
 *
 * == 兩個必須守住的紀律 ==
 *  1. 絕不用 R_BSP_SoftwareDelay() —— 它是忙等,不讓出 CPU。之前就是這樣
 *     把 main_task 的 rpmsg 迴圈餓死的(表現是 A55 那邊 rpmsg 完全沒回應,
 *     看起來像韌體掛了,其實只是永遠排不到)。一律 vTaskDelay()。
 *  2. FSP 的 I2C/UART API 是**非阻塞**的 —— 送出後立刻回傳,完成才進 callback。
 *     所以要用 task notification 等,不能寫完就當它好了。
 */

#include <string.h>

#include "hal_data.h"
#include "common_data.h"   /* g_ioport_ctrl */
#include "FreeRTOS.h"
#include "task.h"

#include "r8_pwm_proto.h"
#include "r8_blackbox.h"
extern void r8_blackbox_pump(void);


/* ===================================================================== */
/* 共用狀態 —— 由本檔的 task 更新,rpmsg callback 讀取                     */
/* ===================================================================== */

/* 這些欄位由 sensor task 單執行緒寫入、rpmsg callback 讀取。
 * 全部是自然對齊的 32-bit,ARM 上單次讀寫本身是原子的,所以不會讀到
 * 半個數值;但**跨欄位**沒有一致性保證(例如 lat 是新的、lon 是舊的)。
 * 對 5 Hz 更新、給人看的遙測而言可接受 —— 但如果之後要拿去做導航解算,
 * 這裡要改成 seqlock(寫入前後各遞增一次序號,讀取端比對)。 */
volatile uint32_t g_gps_frames, g_gps_ck_err, g_gps_last_tick;
volatile uint32_t g_gps_fix, g_gps_nsv, g_gps_hacc_mm, g_gps_pdop, g_gps_itow;
volatile int32_t  g_gps_lat, g_gps_lon, g_gps_alt_mm;

volatile uint32_t g_mag_ok, g_mag_samples, g_mag_err, g_mag_last_tick, g_mag_whoami;
/* 診斷:分辨「Open 失敗」/「傳輸被 NACK」/「callback 沒來」三種失敗 */
volatile uint32_t g_mag_open_err = 0xFFFFFFFFu;   /* R_SCI_B_I2C_Open 的 fsp_err_t */
volatile uint32_t g_mag_last_evt = 0xFFFFFFFFu;   /* 最後一次 I2C callback 的 event */
volatile uint32_t g_mag_timeouts;                 /* i2c_wait() 逾時次數 */
volatile int32_t  g_mag_x, g_mag_y, g_mag_z;

static TaskHandle_t g_sensor_task;

/* ===================================================================== */
/* GPS —— UART 接收環形緩衝                                               */
/* ===================================================================== */

/* 230400 baud = 23 KB/s。4 KB 約可緩衝 178 ms,而 task 每 1 ms 就掏一次,
 * 餘裕兩個數量級。單一生產者(ISR)、單一消費者(task),頭尾各自只由一方
 * 寫入,所以不需要鎖。 */
#define RX_RING_SZ   4096u
#define RX_RING_MASK (RX_RING_SZ - 1u)

static volatile uint8_t  g_rx_ring[RX_RING_SZ];
static volatile uint32_t g_rx_head;   /* 只由 ISR 寫 */
static volatile uint32_t g_rx_tail;   /* 只由 task 寫 */
static volatile uint32_t g_rx_drop;   /* 環滿而丟棄的位元組數 */

void rzv_uart_gps_callback(uart_callback_args_t * p_args)
{
    if (UART_EVENT_RX_CHAR == p_args->event)
    {
        uint32_t h = g_rx_head;
        uint32_t n = (h + 1u) & RX_RING_MASK;
        if (n != g_rx_tail)
        {
            g_rx_ring[h] = (uint8_t) p_args->data;
            g_rx_head    = n;
        }
        else
        {
            g_rx_drop++;   /* 環滿。有值就代表 task 掏得不夠快,是真問題 */
        }
    }
}

static int rx_get(uint8_t * b)
{
    if (g_rx_tail == g_rx_head)
    {
        return 0;
    }
    *b       = g_rx_ring[g_rx_tail];
    g_rx_tail = (g_rx_tail + 1u) & RX_RING_MASK;
    return 1;
}

/* ===================================================================== */
/* GPS —— UBX 幀解析                                                      */
/* ===================================================================== */

/*  B5 62 | class id | len(LE16) | payload | ck_a ck_b
 *  校驗是 8-bit Fletcher,從 class 算到 payload 結尾。
 *  用狀態機逐位元組吃,不需要另外開一個大緩衝重組。 */

#define UBX_SYNC1 0xB5u
#define UBX_SYNC2 0x62u
#define UBX_MAX_PAYLOAD 128u          /* NAV-PVT 是 92,取 128 夠用且不浪費 */

enum { S_S1 = 0, S_S2, S_CLS, S_ID, S_LEN1, S_LEN2, S_PAY, S_CKA, S_CKB };

static uint8_t  u_state, u_cls, u_id, u_cka, u_ckb;
static uint16_t u_len, u_idx;
static uint8_t  u_pay[UBX_MAX_PAYLOAD];
static uint8_t  u_skip;               /* payload 超過緩衝時只算校驗、不存 */

static void ubx_ck(uint8_t c)
{
    u_cka = (uint8_t) (u_cka + c);
    u_ckb = (uint8_t) (u_ckb + u_cka);
}

static uint32_t rd_u32(const uint8_t * p) { return (uint32_t) p[0] | ((uint32_t) p[1] << 8) | ((uint32_t) p[2] << 16) | ((uint32_t) p[3] << 24); }
static uint16_t rd_u16(const uint8_t * p) { return (uint16_t) ((uint16_t) p[0] | ((uint16_t) p[1] << 8)); }
static int32_t  rd_i32(const uint8_t * p) { return (int32_t) rd_u32(p); }

/* NAV-PVT 的欄位位移(u-blox M8 protocol spec 32.10.19) */
static void ubx_on_nav_pvt(const uint8_t * p)
{
    g_gps_itow    = rd_u32(p + 0);
    g_gps_fix     = p[20];
    g_gps_nsv     = p[23];
    g_gps_lon     = rd_i32(p + 24);      /* 1e-7 deg */
    g_gps_lat     = rd_i32(p + 28);
    g_gps_alt_mm  = rd_i32(p + 36);      /* hMSL */
    g_gps_hacc_mm = rd_u32(p + 40);
    g_gps_pdop    = rd_u16(p + 76);      /* 0.01 */
    g_gps_last_tick = (uint32_t) xTaskGetTickCount();
}

static void ubx_feed(uint8_t c)
{
    switch (u_state)
    {
        case S_S1:
            if (UBX_SYNC1 == c) { u_state = S_S2; }
            break;

        case S_S2:
            /* 收到 B5 之後不是 62 —— 但這個位元組本身可能是新的 B5 */
            u_state = (UBX_SYNC2 == c) ? S_CLS : ((UBX_SYNC1 == c) ? S_S2 : S_S1);
            if (S_CLS == u_state) { u_cka = 0u; u_ckb = 0u; }
            break;

        case S_CLS:  u_cls = c; ubx_ck(c); u_state = S_ID;   break;
        case S_ID:   u_id  = c; ubx_ck(c); u_state = S_LEN1; break;
        case S_LEN1: u_len = c; ubx_ck(c); u_state = S_LEN2; break;

        case S_LEN2:
            u_len = (uint16_t) (u_len | ((uint16_t) c << 8));
            ubx_ck(c);
            u_idx  = 0u;
            u_skip = (u_len > UBX_MAX_PAYLOAD) ? 1u : 0u;
            u_state = (0u == u_len) ? S_CKA : S_PAY;
            break;

        case S_PAY:
            ubx_ck(c);
            if (!u_skip) { u_pay[u_idx] = c; }
            if (++u_idx >= u_len) { u_state = S_CKA; }
            break;

        case S_CKA:
            u_state = (c == u_cka) ? S_CKB : S_S1;
            if (S_S1 == u_state) { g_gps_ck_err++; }
            break;

        case S_CKB:
            if (c == u_ckb)
            {
                g_gps_frames++;
                /* NAV-PVT = class 0x01 / id 0x07 */
                if ((0x01u == u_cls) && (0x07u == u_id) && !u_skip && (u_len >= 84u))
                {
                    ubx_on_nav_pvt(u_pay);
                }
            }
            else
            {
                g_gps_ck_err++;
            }
            u_state = S_S1;
            break;

        default:
            u_state = S_S1;
            break;
    }
}

/* ===================================================================== */
/* 羅盤 —— IST8310 over FSP SCI I2C                                       */
/* ===================================================================== */

#define IST_REG_WAI    0x00u
#define IST_REG_STAT1  0x02u
#define IST_REG_DATA   0x03u
#define IST_REG_CNTL1  0x0Au
#define IST_REG_CNTL2  0x0Bu
#define IST_REG_AVG    0x41u
#define IST_REG_PD     0x42u
#define IST_DEVICE_ID  0x10u

#define I2C_NOTIFY_OK   0x1u
#define I2C_NOTIFY_FAIL 0x2u

void rzv_i2c_mag_callback(i2c_master_callback_args_t * p_args)
{
    BaseType_t woken = pdFALSE;
    g_mag_last_evt = (uint32_t) p_args->event;
    uint32_t   v = ((I2C_MASTER_EVENT_TX_COMPLETE == p_args->event) ||
                    (I2C_MASTER_EVENT_RX_COMPLETE == p_args->event))
                 ? I2C_NOTIFY_OK : I2C_NOTIFY_FAIL;

    if (NULL != g_sensor_task)
    {
        xTaskNotifyFromISR(g_sensor_task, v, eSetBits, &woken);
    }
    portYIELD_FROM_ISR(woken);
}

/* 等 callback。逾時回 0 —— I2C 卡住時不能永遠掛著,否則整個 task 停擺,
 * 連 GPS 也一起沒了。 */
static int i2c_wait(void)
{
    R8_SNS_STAGE(5);
    uint32_t v = 0u;
    if (pdTRUE != xTaskNotifyWait(0u, 0xFFFFFFFFu, &v, pdMS_TO_TICKS(20)))
    {
        g_mag_timeouts++;
        return 0;
    }
    return (0u != (v & I2C_NOTIFY_OK)) ? 1 : 0;
}

static int ist_write(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = { reg, val };
    (void) xTaskNotifyStateClear(NULL);
    if (FSP_SUCCESS != R_SCI_B_I2C_Write(&g_i2c_mag_ctrl, buf, 2u, false)) { return 0; }
    return i2c_wait();
}

static int ist_read(uint8_t reg, uint8_t * dst, uint32_t n)
{
    (void) xTaskNotifyStateClear(NULL);
    /* restart = true:寫完暫存器位址不送 STOP,直接 repeated start 轉讀 */
    if (FSP_SUCCESS != R_SCI_B_I2C_Write(&g_i2c_mag_ctrl, &reg, 1u, true)) { return 0; }
    if (!i2c_wait()) { return 0; }

    (void) xTaskNotifyStateClear(NULL);
    if (FSP_SUCCESS != R_SCI_B_I2C_Read(&g_i2c_mag_ctrl, dst, n, false)) { return 0; }
    return i2c_wait();
}

static int ist_init(void)
{
    uint8_t wai = 0u;

    if (!ist_read(IST_REG_WAI, &wai, 1u)) { return 0; }
    g_mag_whoami = wai;
    if (IST_DEVICE_ID != wai) { return 0; }

    if (!ist_write(IST_REG_CNTL2, 0x01u)) { return 0; }   /* soft reset */
    vTaskDelay(pdMS_TO_TICKS(50));
    if (!ist_write(IST_REG_AVG, 0x24u)) { return 0; }     /* X/Y/Z 各 16 次平均 */
    if (!ist_write(IST_REG_PD,  0xC0u)) { return 0; }     /* pulse duration = normal */
    vTaskDelay(pdMS_TO_TICKS(10));
    return 1;
}

static int ist_sample(void)
{
    uint8_t st = 0u, d[6];
    int     i;

    if (!ist_write(IST_REG_CNTL1, 0x01u)) { return 0; }   /* 觸發單次量測 */

    /* 16 次平均約需 6 ms。最多等 10 ms,期間讓出 CPU。 */
    for (i = 0; i < 10; i++)
    {
        vTaskDelay(pdMS_TO_TICKS(1));
        if (!ist_read(IST_REG_STAT1, &st, 1u)) { return 0; }
        if (0u != (st & 0x01u)) { break; }                /* DRDY */
    }
    if (0u == (st & 0x01u)) { return 0; }

    if (!ist_read(IST_REG_DATA, d, 6u)) { return 0; }

    /* 小端 16-bit 有號。原始 LSB 直接上傳,不在 R8 做浮點換算 ——
     * 換算係數(0.3 µT/LSB)放 A55 那邊,跟 PWM 協定把 pclk_hz 丟給
     * A55 自己算是同一個思路:R8 只送事實,不送詮釋。 */
    g_mag_x = (int32_t) (int16_t) ((uint16_t) d[0] | ((uint16_t) d[1] << 8));
    g_mag_y = (int32_t) (int16_t) ((uint16_t) d[2] | ((uint16_t) d[3] << 8));
    g_mag_z = (int32_t) (int16_t) ((uint16_t) d[4] | ((uint16_t) d[5] << 8));
    g_mag_samples++;
    g_mag_last_tick = (uint32_t) xTaskGetTickCount();
    return 1;
}

/* ===================================================================== */
/* Sensor task                                                            */
/* ===================================================================== */

static void sensor_task(void * pv)
{
    fsp_err_t err;
    uint8_t   c;
    uint32_t  next_mag = 0u;
    int       i;

    (void) pv;
    g_sensor_task = xTaskGetCurrentTaskHandle();
    R8_BB_STAGE(20);

    /* --- GPS UART --- */
    err = R_SCI_B_UART_Open(&g_uart_gps_ctrl, &g_uart_gps_cfg);
    R8_BB_STAGE(21);
    /* 開失敗就不再碰 UART,但羅盤還是要跑 —— 一個感測器壞掉不該拖垮另一個 */
    if (FSP_SUCCESS != err) { g_gps_ck_err = 0xFFFFFFFFu; }

    /* --- 羅盤 I2C --- */

    /* ⚠️ 必須自己把 SDA/SCL 設成開汲極。
     *
     * FSP 產生的 pin_data.c 給 P76/P77 的是
     *   DRIVE_B01 | NOISE_FILTER_ON | PERIPHERAL_PIN | SLEW_RATE_FAST | MODE1
     * —— 少了 IOPORT_CFG_NOD_ENABLE。I2C 的兩條線必須開汲極,否則從機拉低 SDA
     * 送 ACK 時會和主機的推挽輸出打架,主機永遠判定 NACK,每次傳輸都 abort。
     *
     * Smart Configurator 那側找不到對應的 configSetting altId(全機沒有任何
     * 專案用過),而 altId 是猜不得的 —— 所以改用公開 API 明寫。
     * FSP 的 SCI I2C 驅動本身完全不碰腳位設定(已查 r_sci_b_i2c.c)。
     *
     * 對照:Linux 的 DTS 對 rsci_i2c7_pins 有寫 drive-open-drain,所以 Linux 讀得到。 */
    {
        const uint32_t od = (uint32_t) IOPORT_CFG_DRIVE_B01
                          | (uint32_t) IOPORT_CFG_NOISE_FILTER_ON
                          | (uint32_t) IOPORT_CFG_PERIPHERAL_PIN
                          | (uint32_t) IOPORT_CFG_SLEW_RATE_FAST
                          | (uint32_t) IOPORT_CFG_NOD_ENABLE
                          | (uint32_t) IOPORT_PERIPHERAL_MODE1;
        (void) R_IOPORT_PinCfg(&g_ioport_ctrl, (bsp_io_port_pin_t) BSP_IO_PORT_07_PIN_06, od);
        (void) R_IOPORT_PinCfg(&g_ioport_ctrl, (bsp_io_port_pin_t) BSP_IO_PORT_07_PIN_07, od);
        R8_BB_STAGE(22);
    }

    err = R_SCI_B_I2C_Open(&g_i2c_mag_ctrl, &g_i2c_mag_cfg);
    R8_BB_STAGE(23);
    g_mag_open_err = (uint32_t) err;
    if (FSP_SUCCESS == err)
    {
        g_mag_ok = (uint32_t) ist_init();
        R8_BB_STAGE(24);
    }

    for (;;)
    {
        /* 掏 UART 環形緩衝。一次最多吃 512 位元組就讓出,避免 GPS 爆量時
         * 把這個迴圈卡死 —— 5 Hz × 約 200 位元組,正常一輪只有幾十個。 */
        R8_SNS_STAGE(1);
        for (i = 0; (i < 512) && rx_get(&c); i++)
        {
            ubx_feed(c);
        }

        /* 羅盤 20 Hz。比 GPS 快是刻意的:磁場變化遠比位置快,
         * 而且 IST8310 單次量測只要 6 ms,20 Hz 綽綽有餘。 */
        if ((uint32_t) xTaskGetTickCount() >= next_mag)
        {
            R8_SNS_STAGE(2);
            next_mag = (uint32_t) xTaskGetTickCount() + pdMS_TO_TICKS(50);
            if (g_mag_ok)
            {
                if (!ist_sample())
                {
                    g_mag_err++;
                    /* 連續失敗就重新初始化一次 —— 熱插拔或匯流排鎖死後能自己回來 */
                    if (0u == (g_mag_err % 20u)) { g_mag_ok = (uint32_t) ist_init(); }
                }
            }
            else if (FSP_SUCCESS == R_SCI_B_I2C_Open(&g_i2c_mag_ctrl, &g_i2c_mag_cfg))
            {
                g_mag_ok = (uint32_t) ist_init();   /* 開機時沒接,之後接上也認得 */
            }
        }

        R8_BB_INC(hb_sensor);
        R8_SNS_STAGE(3);
        r8_blackbox_pump();
        R8_SNS_STAGE(4);
        vTaskDelay(1);      /* 1 ms。絕不能用 R_BSP_SoftwareDelay —— 見檔頭 */
    }
}

void sensors_start(void)
{
    /* 優先權 2:高於 blinky/pwm(1),低於 main_task 的 rpmsg 迴圈,
     * 這樣 GPS 位元組不會被 PWM 迴圈拖延,但也不會反過來壓住 rpmsg。 */
    (void) xTaskCreate(sensor_task, "sensors", 1024, NULL, 2, NULL);
}

/* rpmsg callback 用:把當下快照填進回應結構 */
void sensors_fill(sns_rsp_t * r)
{
    uint32_t now = (uint32_t) xTaskGetTickCount();

    r->gps_frames = g_gps_frames;
    r->gps_ck_err = g_gps_ck_err;
    r->gps_drop   = g_rx_drop;
    r->gps_age_ms = (0u == g_gps_last_tick) ? 0xFFFFFFFFu
                                            : (uint32_t) ((now - g_gps_last_tick) * 1000u / configTICK_RATE_HZ);
    r->gps_fix    = g_gps_fix;
    r->gps_nsv    = g_gps_nsv;
    r->gps_lat    = g_gps_lat;
    r->gps_lon    = g_gps_lon;
    r->gps_alt_mm = g_gps_alt_mm;
    r->gps_hacc_mm= g_gps_hacc_mm;
    r->gps_pdop   = g_gps_pdop;
    r->gps_itow   = g_gps_itow;

    r->mag_ok     = g_mag_ok;
    r->mag_whoami = g_mag_whoami;
    r->mag_samples= g_mag_samples;
    r->mag_err    = g_mag_err;
    r->mag_age_ms = (0u == g_mag_last_tick) ? 0xFFFFFFFFu
                                            : (uint32_t) ((now - g_mag_last_tick) * 1000u / configTICK_RATE_HZ);
    r->mag_x      = g_mag_x;
    r->mag_y      = g_mag_y;
    r->mag_z      = g_mag_z;
    r->mag_open_err = g_mag_open_err;
    r->mag_last_evt = g_mag_last_evt;
    r->mag_timeouts = g_mag_timeouts;
}
