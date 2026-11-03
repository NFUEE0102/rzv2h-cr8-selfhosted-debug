#!/usr/bin/env python3
"""core0-pwm -> core0-pwm-plane: 4-channel servo/ESC firmware for the EVK on Pmod CN2 pins 7-10
(2026-09-16, fixed-wing bench: 1 ESC + 3 servos).

Pin plan (EVK schematic "Pmod Type2/2A (SPI) Connector", all pins Linux-unclaimed on .177):
    CN2-7   P74  GTIOC4A   ESC (motor)      r8_bench pwm 4 a 50 <duty%>
    CN2-8   P75  GTIOC4B   servo 1          r8_bench pwm 4 b 50 <duty%>
    CN2-9   PA6  GTIOC7A   servo 2          r8_bench pwm 7 a 50 <duty%>
    CN2-10  PA4  GTIOC6A   servo 3          r8_bench pwm 6 a 50 <duty%>
    CN2-11  GND  (common ground with the BEC; CN2-12 3.3 V is NOT used)

PA4 can also be GTIOC10A, but GPT10 lives in the second GPT block (0x13020000): the A55 reads that
block as all-ones on the EVK even with CPG clock on / reset off / MSTOP off, so it cannot be verified
from Linux. GPT6 (first block, the proven pwm-demo channel that used to sit on P76) is used instead;
all four channels are then in the 0x13010000 block and readable from Linux for checks.

Everything else the base pwm-demo drove (GPT5 P84/P85 = Linux sci4, GPT6.B P77 / GPT6.A P76,
GPT8 P50 = Linux SCI0-SPI, GPT9 P96/P97 = Linux usb20/sound_clk, GPT7.B PA7 = Linux spi2 SSL, GPT0.A P70)
is removed from the pin configuration so this firmware touches exactly four SoC pins. GPT0 stays as
a module with no pin output: the tick-jitter probe reads its GTCNT as the time base.

pwm_test.c gets the 4-channel group table, the GPT-number map, and a pulse clamp: any non-zero
command is limited to 1000..2000 us and 50..400 Hz; duty 0 (silence / disarm) stays allowed.
Boot behaviour is unchanged: all outputs silent until the A55 sends the first PWMC.

usage: core0_pwm_plane.py <project dir>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import patch, proj_arg, rd, wr  # noqa: E402

P = proj_arg(sys.argv)
CX = f"{P}/configuration.xml"
cx = rd(CX)

if "pa4.gpt6.gtioc6a" in cx:
    print("  configuration.xml: already a plane build")
else:
    # ---- 1. drop the GPT modules and stacks we do not use (5, 8, 9) ----
    for ch in ("5", "8", "9"):
        pat = re.compile(r'    <module id="module\.driver\.timer_on_gpt\.90%s0000">.*?\n    </module>\n' % ch, re.S)
        cx, n = pat.subn("", cx, count=1)
        assert n == 1, f"gpt{ch} module block not found"
        st = f'      <stack module="module.driver.timer_on_gpt.90{ch}0000"/>\n'
        assert cx.count(st) == 1, f"gpt{ch} stack not found"
        cx = cx.replace(st, "", 1)

    # ---- 2. GPT4: A (P74) + B (P75); GPT6: A only (PA4); GPT7: A only (PA6); GPT0: no pin output ----
    def module_block(ch):
        mm = re.search(r'    <module id="module\.driver\.timer_on_gpt\.90%s0000">.*?\n    </module>\n' % ch, cx, re.S)
        assert mm, f"gpt{ch} module block not found"
        return mm

    def set_outputs(ch, a, b):
        global cx
        mm = module_block(ch)
        blk = mm.group(0)
        for key, val in (("gtioca", a), ("gtiocb", b)):
            pat = re.compile(r'(module\.driver\.timer\.%s_output_enabled" value="module\.driver\.timer\.%s_output_enabled\.)(true|false)' % (key, key))
            blk, n = pat.subn(lambda x: x.group(1) + ("true" if val else "false"), blk, count=1)
            assert n == 1, f"gpt{ch} {key} output flag not found"
        cx = cx[:mm.start()] + blk + cx[mm.end():]

    set_outputs("4", True, True)
    set_outputs("6", True, False)
    set_outputs("7", True, False)
    set_outputs("0", False, False)

    # ---- 3. pin configuration: keep only P74/P75 (GPT4), PA4 (GPT6), PA6 (GPT7) ----
    a = cx.index('    <pincfg active="true"')
    b = cx.index('    </pincfg>', a)
    pincfg = cx[a:b]
    lines = pincfg.split("\n")
    head = lines[0]
    keep = [head]
    for ln in lines[1:]:
        if not ln.strip():
            continue
        assert "configSetting" in ln, ln
        if "gpt7.mode.custom.free" in ln or "gpt7.gtioc7a.pa6" in ln or "pa6." in ln:
            keep.append(ln)          # GPT7.A on PA6 stays as-is
        # everything else (gpt0/4/5/6/8/9 pins, PA7) is dropped and GPT4/GPT10 re-added below
    new_pins = '''      <configSetting altId="gpt4.mode.custom.free" configurationId="gpt4.mode"/>
      <configSetting altId="gpt4.gtioc4a.p74" configurationId="gpt4.gtioc4a"/>
      <configSetting altId="p74.gpt4.gtioc4a" configurationId="p74"/>
      <configSetting altId="p74.gpio_mode.gpio_mode_peripheral" configurationId="p74.gpio_mode"/>
      <configSetting altId="gpt4.gtioc4b.p75" configurationId="gpt4.gtioc4b"/>
      <configSetting altId="p75.gpt4.gtioc4b" configurationId="p75"/>
      <configSetting altId="p75.gpio_mode.gpio_mode_peripheral" configurationId="p75.gpio_mode"/>
      <configSetting altId="gpt6.mode.custom.free" configurationId="gpt6.mode"/>
      <configSetting altId="gpt6.gtioc6a.pa4" configurationId="gpt6.gtioc6a"/>
      <configSetting altId="pa4.gpt6.gtioc6a" configurationId="pa4"/>
      <configSetting altId="pa4.gpio_mode.gpio_mode_peripheral" configurationId="pa4.gpio_mode"/>'''
    assert len(keep) == 5, f"expected head + 4 GPT7/PA6 lines, got {len(keep)}: {keep}"
    pincfg_new = "\n".join(keep[:1]) + "\n" + new_pins + "\n" + "\n".join(keep[1:]) + "\n"
    cx = cx[:a] + pincfg_new + cx[b:]
    wr(CX, cx)
    print("  configuration.xml: GPT4 A/B on P74/P75, GPT6.A on PA4, GPT7.A on PA6; GPT5/8/9 removed; GPT0 pinless")

# ---- 5. pwm_test.c: 4-channel table, GPT map, pulse clamp ----
patch(f"{P}/src/pwm_test.c", [
    ("""static const pwm_group_t g_groups[] = {
    { (timer_ctrl_t *) &g_gpt0_ctrl, &g_gpt0_cfg, 1, 0, 1450u,    0u },  /* P70 錨點 */
    { (timer_ctrl_t *) &g_gpt4_ctrl, &g_gpt4_cfg, 0, 1,    0u, 1200u },  /* P95 */
    { (timer_ctrl_t *) &g_gpt5_ctrl, &g_gpt5_cfg, 1, 1, 1100u, 1150u },  /* P84 / P85 */
    { (timer_ctrl_t *) &g_gpt6_ctrl, &g_gpt6_cfg, 1, 1, 1000u, 1050u },  /* P76 / P77 */
    { (timer_ctrl_t *) &g_gpt7_ctrl, &g_gpt7_cfg, 1, 1, 1350u, 1400u },  /* PA6 / PA7 */
    { (timer_ctrl_t *) &g_gpt8_ctrl, &g_gpt8_cfg, 1, 0, 1500u,    0u },  /* P50 錨點 */
    { (timer_ctrl_t *) &g_gpt9_ctrl, &g_gpt9_cfg, 1, 1, 1250u, 1300u },  /* P96 / P97 */
};""",
     """/* core0-pwm-plane(2026-09-16):EVK Pmod CN2 pin 7-10,定翼台架 1 ESC + 3 舵機。
 * GPT0 只當 tick 抖動探針的時基,沒有接腳輸出(has_a = has_b = 0 ⇒ PWMC 會被擋)。
 * us_a/us_b 只是文件上的「解鎖/置中」參考值;開機一律靜默,等 A55 下第一筆 PWMC。 */
static const pwm_group_t g_groups[] = {
    { (timer_ctrl_t *) &g_gpt0_ctrl,  &g_gpt0_cfg,  0, 0,    0u,    0u },  /* 時基,無輸出 */
    { (timer_ctrl_t *) &g_gpt4_ctrl,  &g_gpt4_cfg,  1, 1, 1000u, 1500u },  /* P74 ESC / P75 舵機1 (CN2-7/8) */
    { (timer_ctrl_t *) &g_gpt7_ctrl,  &g_gpt7_cfg,  1, 0, 1500u,    0u },  /* PA6 舵機2 (CN2-9) */
    { (timer_ctrl_t *) &g_gpt6_ctrl,  &g_gpt6_cfg,  1, 0, 1500u,    0u },  /* PA4 舵機3 (CN2-10) */
};

/* 脈寬鉗位:舵機/ESC 的安全範圍。duty 0 = 靜默(解除武裝)永遠允許。 */
#define PLANE_PULSE_MIN_US   1000u
#define PLANE_PULSE_MAX_US   2000u
#define PLANE_FREQ_MIN_HZ      50u
#define PLANE_FREQ_MAX_HZ     400u"""),
    ("""        case 0: return 0;
        case 4: return 1;
        case 5: return 2;
        case 6: return 3;
        case 7: return 4;
        case 8: return 5;
        case 9: return 6;
        default: return -1;""",
     """        case 0:  return 0;
        case 4:  return 1;
        case 7:  return 2;
        case 6:  return 3;
        default: return -1;"""),
    ("""    uint32_t period = (uint32_t) period64;
    uint32_t duty   = (uint32_t) (((uint64_t) period * (uint64_t) duty_permille) / 1000u);
""",
     """    uint32_t period = (uint32_t) period64;
    uint32_t duty   = (uint32_t) (((uint64_t) period * (uint64_t) duty_permille) / 1000u);

    /* core0-pwm-plane:頻率限 50..400 Hz;非零脈寬鉗在 1000..2000 us。
     * 鉗位後的實際值會回報在 duty_counts,A55 端可以看出有沒有被夾。
     * 高解析:duty_permille 的 bit31 set ⇒ 低 31 位是 1e-5 單位(0.001 %),
     * 50 Hz 下一格 = 0.2 us(千分比只有 20 us 一格,舵機看得出階梯)。 */
    if (0u != (duty_permille & 0x80000000u))
    {
        uint32_t v = duty_permille & 0x7FFFFFFFu;
        if (v > 100000u) { return PWM_ERR_BAD_DUTY; }
        duty = (uint32_t) (((uint64_t) period * (uint64_t) v) / 100000u);
    }
    if ((freq_hz < PLANE_FREQ_MIN_HZ) || (freq_hz > PLANE_FREQ_MAX_HZ))
    {
        return PWM_ERR_RANGE;
    }
    if (0u != duty)
    {
        const uint32_t min_counts = (PWM_PCLK_HZ / 1000000u) * PLANE_PULSE_MIN_US;
        const uint32_t max_counts = (PWM_PCLK_HZ / 1000000u) * PLANE_PULSE_MAX_US;
        if (duty < min_counts) { duty = min_counts; }
        if (duty > max_counts) { duty = max_counts; }
    }

    /* 週期沒變且計時器在跑 ⇒ 只改 duty:R_GPT_DutyCycleSet 寫的是緩衝暫存器
     * (GTCCRC/GTCCRE),下個週期邊界才生效,脈衝相位不動、不重啟計數器。
     * 舊路徑每筆都 Stop/Start,搖桿連續微調時脈衝整段亂跳(09-16 台架實見)。 */
    {
        gpt_instance_ctrl_t * ic = (gpt_instance_ctrl_t *) g->ctrl;
        if ((ic->p_reg->GTPR == (period - 1u)) && (0u != (ic->p_reg->GTCR & 1u)))
        {
            if (FSP_SUCCESS != R_GPT_DutyCycleSet(g->ctrl, duty,
                                    use_b ? GPT_IO_PIN_GTIOCB : GPT_IO_PIN_GTIOCA))
            {
                return PWM_ERR_DUTY;
            }
            if (NULL != out_period) { *out_period = period; }
            if (NULL != out_duty)   { *out_duty   = duty;   }
            return 0;
        }
    }
"""),
    # the early-exit above needs the BAD_DUTY check (> 1000) relaxed for the hi-res encoding
    ("""    if (duty_permille > 1000u)   return PWM_ERR_BAD_DUTY;""",
     """    if ((0u == (duty_permille & 0x80000000u)) && (duty_permille > 1000u)) return PWM_ERR_BAD_DUTY;"""),
], done_marker="PLANE_PULSE_MIN_US")
print("variant: core0-pwm-plane applied")
