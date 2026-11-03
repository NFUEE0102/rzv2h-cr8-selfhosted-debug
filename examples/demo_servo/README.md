# demo_servo: find a bug on the CR8 by single-stepping

A 60-line task with one deliberate bug, used to show that the self-hosted debugger does the
whole job: break on a condition, step, read locals, patch a value live, fix, redeploy.

## The firmware

`cr8_demo.elf` is the `core0-demo` variant: the `core0-pwm-plane` firmware plus
`demo_servo.c` (this directory, also `firmware/variants/files/demo_servo.c`), compiled
`-O0` so every local is visible.

Every 250 ms `demo_servo_step()` takes the next angle from a 10-entry table (0, 10, …, 90°),
converts it with `angle_to_pulse_us()` and writes it to **GPT4.B = P75 = Pmod CN2 pin 8**
(50 Hz servo pulse, 1000–2000 µs). It mirrors its state to DDR at `0x439FF000`
(`+0x08` angle, `+0x0C` pulse µs), readable from Linux with `busybox devmem`.

The prebuilt `cr8_demo.elf` in this directory is the **buggy** build, md5 `df6f1965…`.

## The bug

```c
uint16_t angle_to_pulse_us(uint16_t deg)
{
    uint16_t scaled = deg * 1000;          /* 70 * 1000 = 70000 does not fit in 16 bits */
    uint16_t pulse  = 1000 + scaled / 90;
    return pulse;
}
```

| angle | `deg * 1000` | stored in `uint16_t` | pulse | should be |
|---|---|---|---|---|
| 60° | 60000 | 60000 | 1666 µs | 1666 µs |
| 70° | 70000 | 4464 | **1049 µs** | 1777 µs |
| 80° | 80000 | 14464 | **1160 µs** | 1888 µs |
| 90° | 90000 | 24464 | **1271 µs** | 2000 µs |

On a scope (or a servo) the pulse climbs 1.00 → 1.67 ms and then drops back to 1.05 ms.
Looking at the waveform tells you nothing about which line is wrong.

## Walkthrough in e² studio

Start with the desktop launcher and attach (see the [README](../../README.md)). Then:

1. Open `src/demo_servo.c`, double-click the gutter at **line 54**
   (`uint16_t scaled = deg * 1000;`). Right-click the marker → Breakpoint Properties →
   **Common** → Condition `deg >= 70` → Apply and Close. Resume (F8). It stops within a
   sweep; Variables shows `deg = 70` (or 80/90).
2. **Step Over** (F6): `scaled = 4464`. Step Over again: `pulse = 1049`. The declaration
   `uint16_t scaled` is the bug.
3. Live patch without rebuilding: **Step Return** (F7) back into `demo_servo_step()`, then
   **one more Step Over** so the assignment `pulse_us = 1049` completes (skip this and the
   edited value is overwritten by the return value). In Variables set `pulse_us` to `1777`,
   Resume. The next stop (deg = 80) shows the previous iteration applied 1777 µs: the scope
   reads 1.78 ms while the core is halted, and `busybox devmem 0x439FF00C 32` on the EVK
   reads `0x6F1`.
4. Real fix: Disconnect, change line 54 to `uint32_t scaled = (uint32_t) deg * 1000u;`,
   **Project → Build Project** (Ctrl+B), click **CR8 Redeploy**. The sweep is now clean
   (70/80/90° → 1777/1888/2000 µs). Press Debug again if you want to confirm under the
   debugger.
5. To put the bug back for the next run: restore line 54, Ctrl+B, CR8 Redeploy.

Notes: right-click → *Build Selected File(s)* only compiles that file and does not link a
new ELF; use Build Project. If the Variables view shows `scaled`/`pulse` as 1799 at the
breakpoint, that is the old stack content before line 54 has executed, not the bug.

`DEMO.zh-TW.md` is the Traditional Chinese presenter script for the same sequence, with
timings and the things that go wrong.
