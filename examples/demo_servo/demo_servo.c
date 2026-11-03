/*
 * demo_servo.c -- single-step / find-the-bug / fix-it demo for the CR8.
 *
 * Every 250 ms the task below takes the next angle from a table (0..90 deg),
 * converts it to a servo pulse and writes it to GPT4.B = P75 = Pmod CN2 pin 8
 * (servo 1 of the fixed-wing bench; 50 Hz, 1000..2000 us).
 *
 * There is one deliberate bug in angle_to_pulse_us(): the intermediate
 * product is stored in a 16-bit variable, so 70 deg and above wrap around
 * and the pulse drops back to ~1049 us instead of reaching 1777 us.
 * Watch it on the scope, then find it with the debugger:
 *   breakpoint in demo_servo_step() with condition  deg >= 70
 *   Step Into angle_to_pulse_us(), one Step Over -> 'scaled' shows 4464.
 *   Fix on the fly: edit 'pulse_us' in the Variables view, Resume.
 *   Real fix: cast to 32 bits (see the comment), rebuild, redeploy.
 *
 * Built at -O0 on purpose so every local is visible while stepping.
 *
 * Status is mirrored to DDR at DEMO_STATUS_ADDR (inside the black-box page,
 * readable from Linux: busybox devmem 0x439FF008 32 -> current degrees).
 */
#pragma GCC optimize ("O0")

#include <stdint.h>

extern int pwm_apply(uint32_t gpt, uint32_t use_b, uint32_t freq_hz,
                     uint32_t duty_permille, uint32_t * out_period, uint32_t * out_duty);

#define DEMO_GPT          (4u)     /* GPT4 ... */
#define DEMO_USE_B        (1u)     /* ... output B = P75 = CN2 pin 8 */
#define DEMO_FREQ_HZ      (50u)
#define DEMO_STATUS_ADDR  (0x439FF000u)
#define DEMO_MAGIC        (0x4F4D4544u)   /* "DEMO" */

typedef struct
{
    uint32_t magic;
    uint32_t calls;      /* +0x04 how many steps so far */
    uint32_t deg;        /* +0x08 current angle          */
    uint32_t pulse_us;   /* +0x0C pulse actually applied */
    uint32_t rc;         /* +0x10 pwm_apply() result     */
} demo_status_t;

#define DEMO_STATUS  ((volatile demo_status_t *) DEMO_STATUS_ADDR)

uint16_t angle_to_pulse_us(uint16_t deg);
void     demo_servo_step(void);

static const uint16_t angle_table[10] = { 0, 10, 20, 30, 40, 50, 60, 70, 80, 90 };

/* 0..90 degrees -> 1000..2000 us servo pulse */
uint16_t angle_to_pulse_us(uint16_t deg)
{
    uint16_t scaled = deg * 1000;          /* BUG: 70 * 1000 = 70000 does not fit in 16 bits.
                                              Fix: uint32_t scaled = (uint32_t) deg * 1000u; */
    uint16_t pulse  = 1000 + scaled / 90;  /* 1000 + (0..90)*1000/90 */
    return pulse;
}

/* called from the pwm_test_entry() loop every 250 ms */
void demo_servo_step(void)
{
    static uint32_t idx = 0;
    uint32_t period = 0, duty = 0;

    uint16_t deg      = angle_table[idx];
    uint16_t pulse_us = angle_to_pulse_us(deg);

    /* bit31 selects the 1e-5 duty encoding: pulse_us / 20000 us * 1e5 = pulse_us * 5 */
    int rc = pwm_apply(DEMO_GPT, DEMO_USE_B, DEMO_FREQ_HZ,
                       0x80000000u | ((uint32_t) pulse_us * 5u), &period, &duty);

    DEMO_STATUS->magic    = DEMO_MAGIC;
    DEMO_STATUS->calls   += 1u;
    DEMO_STATUS->deg      = deg;
    DEMO_STATUS->pulse_us = pulse_us;
    DEMO_STATUS->rc       = (uint32_t) rc;

    idx = (idx + 1u) % 10u;
}
