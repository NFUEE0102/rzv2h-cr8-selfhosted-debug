#!/usr/bin/env python3
"""core1 echo project -> core1 UART demo firmware (devkit docs/12): RSCI5 at 115200 on P72 (TX,
Pmod CN6-8) / P73 (RX, CN3-8), driven over rpmsg with the UARC/UARS protocol (extra/r8_uart_proto.h),
sharing the endpoint with the PWM/JITQ commands by magic. Port of make_core1_uart.py
(assets/core1-uart-20260830). Remember: a module added to configuration.xml by hand needs its
<stack> entry too, or the generator silently skips it -- the UART one is inserted here as a stack.
usage: core1_uart.py <project dir>
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import patch, proj_arg, rd, wr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
P = proj_arg(sys.argv)
EXTRA = os.path.join(HERE, "..", "extra")
for f in ("r8_uart_proto.h", "r8_uart_demo.c"):
    shutil.copy2(os.path.join(EXTRA, f), os.path.join(P, "src", f))
print("  r8_uart_proto.h / r8_uart_demo.c -> src/")

MODULE = '''    <module id="module.driver.uart_on_sci_b_uart.20260830">
      <property id="module.driver.uart.name" value="g_uart_demo"/>
      <property id="module.driver.uart.channel" value="5"/>
      <property id="module.driver.uart.data_bits" value="module.driver.uart.data_bits.data_bits_8"/>
      <property id="module.driver.uart.parity" value="module.driver.uart.parity.parity_off"/>
      <property id="module.driver.uart.stop_bits" value="module.driver.uart.stop_bits.stop_bits_1"/>
      <property id="module.driver.uart.baud" value="115200"/>
      <property id="module.driver.uart.baudrate_modulation" value="module.driver.uart.baudrate_modulation.disabled"/>
      <property id="module.driver.uart.baudrate_max_err" value="5"/>
      <property id="module.driver.uart.flow_control" value="module.driver.uart.flow_control.rts"/>
      <property id="module.driver.uart.pin_control_port" value="module.driver.uart.pin_control_port.PORT_DISABLE"/>
      <property id="module.driver.uart.pin_control_pin" value="module.driver.uart.pin_control_pin.PIN_DISABLE"/>
      <property id="module.driver.uart.clk_src" value="module.driver.uart.clk_src.int_clk"/>
      <property id="module.driver.uart.rx_edge_start" value="module.driver.uart.rx_edge_start.falling_edge"/>
      <property id="module.driver.uart.noisecancel_en" value="module.driver.uart.noisecancel_en.disabled"/>
      <property id="module.driver.uart.rx_fifo_trigger" value="module.driver.uart.rx_fifo_trigger.8"/>
      <property id="module.driver.uart.rs485.de_enable" value="module.driver.uart.rs485.de_enable.disabled"/>
      <property id="module.driver.uart.rs485.de_polarity" value="module.driver.uart.rs485.de_polarity.high"/>
      <property id="module.driver.uart.rs485.de_assertion_time" value="1"/>
      <property id="module.driver.uart.rs485.de_negation_time" value="1"/>
      <property id="module.driver.uart.half_data.enable" value="module.driver.uart.half_data.enable.disabled"/>
      <property id="module.driver.uart.callback" value="rzv_uart_demo_callback"/>
      <property id="module.driver.uart.rxi_ipl" value="14"/>
      <property id="module.driver.uart.txi_ipl" value="14"/>
      <property id="module.driver.uart.tei_ipl" value="14"/>
      <property id="module.driver.uart.eri_ipl" value="14"/>
    </module>
'''
PINCFG = '''      <configSetting altId="rsci5.mode.custom.free" configurationId="rsci5.mode"/>
      <configSetting altId="rsci5.txd5_mosi5_sda5.p72" configurationId="rsci5.txd5_mosi5_sda5"/>
      <configSetting altId="p72.rsci5.txd5_mosi5_sda5" configurationId="p72"/>
      <configSetting altId="p72.gpio_mode.gpio_mode_peripheral" configurationId="p72.gpio_mode"/>
      <configSetting altId="rsci5.rxd5_miso5_scl5.p73" configurationId="rsci5.rxd5_miso5_scl5"/>
      <configSetting altId="p73.rsci5.rxd5_miso5_scl5" configurationId="p73"/>
      <configSetting altId="p73.gpio_mode.gpio_mode_peripheral" configurationId="p73.gpio_mode"/>
'''
COMPONENT = '''    <component apiversion="" class="HAL Drivers" condition="" group="all" subgroup="r_sci_b_uart" variant="" vendor="Renesas" version="3.1.0">
      <description>SCI UART</description>
      <originalPack>Renesas.RZV.3.1.0.pack</originalPack>
    </component>
'''
cx = rd(f"{P}/configuration.xml")
if "g_uart_demo" not in cx:
    a = cx.index('    <module id="module.driver.mhu_b_ns.')
    cx = cx[:a] + MODULE + cx[a:]
    a2 = cx.index('      <configSetting altId="gpt6.mode.custom.free"')
    cx = cx[:a2] + PINCFG + cx[a2:]
    if 'subgroup="r_sci_b_uart"' not in cx:
        a3 = cx.index('    <component apiversion="" class="HAL Drivers" condition="" group="all" subgroup="r_gtm"')
        cx = cx[:a3] + COMPONENT + cx[a3:]
    st = '      <stack module="module.driver.ioport_on_ioport.0"/>'
    assert cx.count(st) == 1
    cx = cx.replace(st, st + '\n      <stack module="module.driver.uart_on_sci_b_uart.20260830"/>', 1)
    wr(f"{P}/configuration.xml", cx)
    print("  configuration.xml: SCI UART component + module + stack + rsci5 pincfg")

patch(f"{P}/src/rpmsg_demo.c", [
    ('#include "r8_pwm_proto.h"', '#include "r8_pwm_proto.h"\n#include "r8_uart_proto.h"'),
    ("""    /* pwm-demo:SNSQ(感測器查詢)已移除 —— 這種封包會走最後的回聲路徑 */

""",
     """    /* pwm-demo:SNSQ(感測器查詢)已移除 —— 這種封包會走最後的回聲路徑 */

    /* ---- UART 展示(core1,r8_uart_proto v1)--------------------------- */
    if (len >= sizeof(uart_cmd_t))
    {
        const uart_cmd_t * uc = (const uart_cmd_t *) data;
        if (UART_CMD_MAGIC == uc->magic)
        {
            extern int32_t  uart_demo_send(const uint8_t *, uint32_t);
            extern uint32_t uart_demo_read(uint8_t *, uint32_t);
            extern uint32_t uart_demo_tx_total(void);
            extern uint32_t uart_demo_rx_total(void);
            extern uint32_t uart_demo_rx_dropped(void);
            static uart_rsp_t ur;          /* 412B,別佔 callback 堆疊 */
            memset(&ur, 0, sizeof(ur) - UART_DATA_MAX);
            ur.magic   = UART_RSP_MAGIC;
            ur.abi_ver = UART_ABI_VER;
            if (UART_ABI_VER != uc->abi_ver)
            {
                ur.status = UART_ERR_ABI;
            }
            else if (UART_OP_SEND == uc->op)
            {
                ur.status = uart_demo_send(uc->data, uc->len);
            }
            else if (UART_OP_QUERY == uc->op)
            {
                ur.rx_len = uart_demo_read(ur.data, UART_DATA_MAX);
            }
            else
            {
                ur.status = UART_ERR_BADOP;
            }
            ur.tx_total   = uart_demo_tx_total();
            ur.rx_total   = uart_demo_rx_total();
            ur.rx_dropped = uart_demo_rx_dropped();
            (void) r8_send_reply(cb_rp_ept, &ur, (int) sizeof(ur));
            return RPMSG_SUCCESS;
        }
    }

"""),
], done_marker="UART_CMD_MAGIC")
patch(f"{P}/src/blinky_thread_entry.c", [
    ("""    {
        extern void r8_blackbox_pump(void);""",
     """    {   /* core1-uart:RSCI5 展示通道(TX=P72=Pmod CN6-8、RX=P73=CN3-8,115200)*/
        extern void uart_demo_start(void);
        uart_demo_start();
    }
    {
        extern void r8_blackbox_pump(void);"""),
], done_marker="uart_demo_start")
print("variant: core1-uart applied")
