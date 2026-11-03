/* CR8 core1 的 UART 展示:RSCI5 @ P72(TX,Pmod CN6-8)/ P73(RX,CN3-8),
 * 115200 8N1。A55 經 rpmsg 下 SEND / QUERY(見 r8_uart_proto.h)。
 *
 * RX 走中斷逐字進 ring(1KB,滿了丟新資料並計數);TX 用 FSP 非同步寫,
 * tx_busy 期間再來的 SEND 回 UART_ERR_TXBUSY(A55 端序列化 + 重試,實務碰不到)。
 * callback 在中斷上下文 —— 只動 ring 與計數,不碰 rpmsg(doc 16 紀律)。 */
#include <string.h>
#include "hal_data.h"
#include "r8_uart_proto.h"

#define RX_RING_SZ  1024u

static volatile uint8_t  g_rx_ring[RX_RING_SZ];
static volatile uint32_t g_rx_head = 0u;      /* ISR 寫 */
static volatile uint32_t g_rx_tail = 0u;      /* task 讀 */
static volatile uint32_t g_rx_total = 0u;
static volatile uint32_t g_rx_dropped = 0u;
static volatile uint32_t g_tx_total = 0u;
static volatile uint32_t g_tx_busy = 0u;
static uint8_t           g_tx_buf[UART_DATA_MAX];

void rzv_uart_demo_callback (uart_callback_args_t * p_args)
{
    switch (p_args->event)
    {
        case UART_EVENT_RX_CHAR:
        {
            uint32_t next = (g_rx_head + 1u) % RX_RING_SZ;
            if (next != g_rx_tail)
            {
                g_rx_ring[g_rx_head] = (uint8_t) p_args->data;
                g_rx_head = next;
            }
            else
            {
                g_rx_dropped++;
            }
            g_rx_total++;
            break;
        }

        case UART_EVENT_TX_COMPLETE:
            g_tx_busy = 0u;
            break;

        default:
            break;
    }
}

void uart_demo_start (void)
{
    (void) R_SCI_B_UART_Open(&g_uart_demo_ctrl, &g_uart_demo_cfg);
}

int32_t uart_demo_send (const uint8_t * p, uint32_t n)
{
    if (n > UART_DATA_MAX)
    {
        n = UART_DATA_MAX;
    }
    if (g_tx_busy)
    {
        return UART_ERR_TXBUSY;
    }
    g_tx_busy = 1u;
    memcpy(g_tx_buf, p, n);
    if (FSP_SUCCESS != R_SCI_B_UART_Write(&g_uart_demo_ctrl, g_tx_buf, n))
    {
        g_tx_busy = 0u;
        return UART_ERR_WRITE;
    }
    g_tx_total += n;
    return 0;
}

uint32_t uart_demo_read (uint8_t * dst, uint32_t max)
{
    uint32_t n = 0u;
    while ((g_rx_tail != g_rx_head) && (n < max))
    {
        dst[n++] = g_rx_ring[g_rx_tail];
        g_rx_tail = (g_rx_tail + 1u) % RX_RING_SZ;
    }
    return n;
}

uint32_t uart_demo_tx_total (void)   { return g_tx_total; }
uint32_t uart_demo_rx_total (void)   { return g_rx_total; }
uint32_t uart_demo_rx_dropped (void) { return g_rx_dropped; }
