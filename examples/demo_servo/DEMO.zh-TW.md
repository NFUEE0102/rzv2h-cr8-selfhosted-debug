# 展示腳本：在 RZ/V2H 的 CR8 上單步除錯並修掉一個 bug（不接 J-Link）

**一句話**：A55 上的 Linux 就是除錯器。e² studio 看到的畫面跟接 J-Link 一樣，但中間沒有任何探針。

## 硬體

| 東西 | 狀態 |
|---|---|
| EVK .177 | DSW1-7 **ON**（MD_BOOT3=1，上電時鎖存；撥完要斷電再開） |
| 示波器 .189 | C3 = Pmod CN2 pin 8（P75，GPT4.B），5 ms/div，看脈寬 |
| 伺服機（可選） | 接 CN2 pin 8 訊號、pin 11 GND，電源走 BEC |
| 韌體 | `/lib/firmware/cr8_demo.elf` = `.168:~/rzv2h-onboard-dev/cr8-fw/build/core0-demo`（有 bug 的版本） |

## 示範程式（`src/demo_servo.c`，60 行，-O0）

每 250 ms 從角度表取 0,10,…,90 度 → `angle_to_pulse_us()` → 寫到 CN2 pin 8。

```c
uint16_t angle_to_pulse_us(uint16_t deg)
{
    uint16_t scaled = deg * 1000;          // BUG：70*1000 = 70000 塞不進 16 位元 → 4464
    uint16_t pulse  = 1000 + scaled / 90;
    return pulse;
}
```

正確：1000 → 2000 µs 線性爬升。有 bug：到 60 度 1666 µs 之後掉回 1049 / 1160 / 1271 µs。

## 流程（約 8 分鐘）

### 0. 開場（桌面一鍵）
.168 桌面點 **CR8 Debug (e2 studio)**。終端跑三行狀態後 e² studio 開在 `ws_cr8dbg`。

### 1. 看症狀（30 秒）
示波器：脈寬一路爬到 1.67 ms，然後突然掉到 1.05 ms 再慢慢爬。伺服機掃到 2/3 就往回跳。
「程式只有 60 行，誰看得出哪裡錯？」

### 2. 附掛 + 條件中斷點（1 分鐘）
Run → Debug Configurations → GDB Hardware Debugging → **CR8 core0 via OpenOCD dmem** → Debug。
核停住（通常停在 FreeRTOS 排程器裡）。
開 `src/demo_servo.c`，在 `uint16_t scaled = deg * 1000;` 那行（第 54 行）雙擊設中斷點，
右鍵 → Breakpoint Properties → Condition：`deg >= 70`。Resume（F8）。
→ 停在 `angle_to_pulse_us (deg=70)`。Variables 看到 `deg = 70`。

### 3. 單步現形（1 分鐘）
Step Over（F6）一次 → `scaled = 4464`。「70 × 1000 怎麼會是 4464？」
再 Step Over → `pulse = 1049`。
指著宣告：`uint16_t scaled`。16 位元最大 65535，70000 繞回去變 4464。

### 4. 現場糾錯，不改碼（1 分鐘）
Step Return（F7）回到 `demo_servo_step`，**再 Step Over 一次**（讓 `pulse_us = 1049` 這個指派做完；
不多按這一下，改的值會被回傳值蓋掉）。
Variables 裡把 `pulse_us` 改成 **1777**，Resume。
→ 下一拍停在 `deg=80` 時，示波器凍在 **1.78 ms**（核停著，GPT 硬體照輸出）。
「核是活的，我們剛剛替它算對了一拍。」

### 5. 真正修掉（2 分鐘）
Disconnect（插頭圖示）。
把第 54 行改成 `uint32_t scaled = (uint32_t) deg * 1000u;`，Ctrl+B 建置（約 25 秒）。
桌面點 **CR8 Redeploy**（停 OpenOCD → 送 ELF → 重啟 core0 → 重啟 OpenOCD，約 20 秒）。
示波器：1.00 → 2.00 ms 乾乾淨淨。想再附掛確認就再按一次 Debug。

### 6. 收尾
關 e² studio，終端自動關隧道與 OpenOCD。
**還原 bug 給下一次展示**：把第 54 行改回 `uint16_t scaled = deg * 1000;`，Ctrl+B，CR8 Redeploy。

## 已實測（2026-11-03，gdb 批次）
條件中斷點命中 deg=70 → Step Over 後 `scaled = 4464`、`pulse = 1049` → Step Return + Step Over 後
`pulse_us = 1049` → set 1777 → 下一拍狀態字 `{deg=70, pulse_us=1777}`、示波器 1.78 ms →
改 cast 重建、Redeploy 後 70/80/90 度 = 1777/1888/2000 → 還原後 bug 回來。

## 會踩到的
* **展示中不要在 OpenOCD 開著時重啟 CR8**（`start-cr8.sh`、`restart-r8-pair.sh`、`echo stop`）：整板卡死要斷電。
  Redeploy 按鈕已經照正確順序做，別手動繞過它。
* 中斷點一律硬體中斷點（Eclipse 會自動用 hw），一顆核 6 個。
* `cortex_r4 maskisr on` 已在設定檔裡：單步時遮罩中斷，不然每一步都被 1 kHz tick 帶進 `IRQ_Handler`。
  代價是單步期間 tick 會漏，對示範無影響。
* 核停著時 PWM 停在最後的值、黑盒子 tick 不走、rpmsg 逾時 —— 這是示範的一部分，講出來。
* e² studio 第一次開 `tasks.c` 會問「大檔案精簡模式」：按 Yes 把門檻拉到 20000 行，不然在那個檔案不能點行號設中斷點。
* 示波器 PAVA 只有 3 位有效數字；要看 µs 級差異讀狀態字 `busybox devmem 0x439FF00C 32`。

## 狀態字（Linux 端隨時可看，不打擾 R8）
`0x439FF000` magic "DEMO"、`+4` 次數、`+8` 角度、`+C` 脈寬 µs、`+10` pwm_apply 回傳值。
