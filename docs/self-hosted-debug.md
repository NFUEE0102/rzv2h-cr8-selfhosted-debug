# How the self-hosted CR8 debug works, and what we had to find out

Everything a J-Link does to a Cortex-R8 is a sequence of reads and writes to that core's
CoreSight debug registers. On the RZ/V2H those registers are also mapped on the system bus,
so the A55 can do the same reads and writes from Linux. OpenOCD's `dmem` adapter (written for
TI K3 parts) turns `/dev/mem` into a debug access port; the rest is the stock OpenOCD
`cortex_r4` target and the stock e² studio *GDB Hardware Debugging* launch type.

This page records the facts from the hardware manual, the order in which the debug region
can be touched safely, and the three things that did not work out of the box.

## What the hardware manual says (R01UH1032EJ0130, section 4.9)

| Fact | Where |
|---|---|
| Debug components occupy a 4 MB window: CoreSight (CST) at `0x1F00_0000`, CA55 at `0x1F40_0000`, CR8 at `0x1F80_0000`. CR8 Core0 Debug `0x1F81_0000`, Core0 PMU `0x1F81_1000`, Core1 Debug `0x1F81_2000`, Core1 PMU `0x1F81_3000`, CTIs `0x1F81_8000/9000`, ETMs `0x1F81_C000/D000`. | Table 4.9-6 |
| "The CoreSight Debug Components area, CA55 Debug Components area, and CR8 Debug Components area can be accessed via the system bus and APB-AP." | Note under Table 4.9-6 |
| Debug connection mode is "No authentication" by default; SEC authentication only on secure products. | 4.9.3.1 |
| `MD_BOOT3` = 0 normal operation, 1 debug operation. Captured by SYS on the rising edge of `PRST_N`; must be 1 at power-on even if the debugger connects later. In normal mode the CST "is not released from the reset and no clock signal is supplied". | 1.9.3, 4.4.7.4 / 4.4.7.5, Table 4.9-3 |
| `SYS_LSI_MODE` (`0x1043_0300`) bit 9 `STAT_DEBUGEN` mirrors `MD_BOOT3`. `SYS_LSI_DEVID` (`0x1043_0304`) reads `x847_A447`. | 4.3.3.2.81 |
| CR8 and CST are in different power domains; the APB between them is in the "communication interrupted" state by default and is opened by the `CPG_LP_CR8_CTL3` (`0x1042_0C44`) handshake: write bits 16–21, wait for bits 8–13. In debug mode this must be done before releasing the CR8 reset. | 2.2.4.6, 2.2.4.9, Table 2.2-51 |

On the EVK the switch is **DSW1-7** (verified: `SYS_LSI_MODE` reads `0x00013C04` with it
off and `0x00013E04` with it on, after a power cycle). The Linux `rz_rproc` driver writes
`CPG_LP_CR8_CTL3 = 0x003F0000` when it starts the CR8 cluster, so the handshake happens
whenever remoteproc starts a core; nothing extra is needed.

## Safe probing order

1. `SYS_LSI_MODE` bit 9 must be 1. If not, nothing in the debug window has a clock.
2. The CST ROM table at `0x1F00_0000` is readable in debug mode as soon as Linux is up
   (`CIDR3` at `+0xFFC` = `0xB1`). Its entries list every component, including the CR8
   ROM table at `0x1F80_0000`.
3. **Only after the CR8 cluster is up** — `CPG_LP_CR8_CTL3` bit 12 (`CSYSACK_DBG`) = 1,
   which in practice means `/sys/class/remoteproc/remoteproc1/state` = `running` — read
   `0x1F80_0FFC` (CR8 ROM table) and `0x1F81_0000` (Core0 debug).

Breaking step 3 is not a bus error: the read never completes, the A55 core that issued it
is stuck, the board drops off the network, and only a power cycle brings it back. We hit this
once. `debug/r8ocd.sh` checks `CTL3` before launching OpenOCD; `r8dbg.py` checks it before
touching the registers.

## What the Core0 debug unit reports

| Register | Value | Meaning |
|---|---|---|
| CIDR / PIDR | part `0xC18`, designer Arm | Cortex-R8 debug unit |
| `DBGDIDR` | `0x3513A003` | ARMv7 debug, 6 breakpoints, 4 watchpoints, 2 context-ID comparators, PC sample register present |
| `DBGAUTHSTATUS` | `0xF0` | invasive and non-invasive debug enabled, no unlock code needed |
| `DBGDEVID` | `0x00000F10` | |
| `DBGPCSR` (`+0x84`) | | PC sampling without halting; works while the firmware runs (tested: a 20-sample histogram resolved to `metal_io_read` / `rpmsg_virtio_wait_remote_ready` / `vTaskSwitchContext`) |

## Three things that did not work out of the box

### 1. The memory-mapped lock

After a CR8 cluster reset the debug registers come up with the software lock engaged
(`DBGLSR` = `0x3`). Writes from the system bus are then silently dropped. OpenOCD never
writes `DBGLAR` because through a real APB-AP the lock does not apply — through `dmem` it
does. Symptom: *Examination succeed*, but `halt` times out ("timeout waiting for DSCR bit
change") and `DSCR.HDBGen` never gets set, so breakpoints never fire either.

Fix in `debug/cr8-dmem.cfg`: an `examine-end` event handler writes `DBGLAR = 0xC5ACCE55`
and sets `DSCR` bit 14 (`HDBGen`) through `dap apreg`.

### 2. Breakpoint registers need a context synchronisation

`BVR`/`BCR` written from the system bus only become visible to the core at its next
context-synchronisation event. OpenOCD programs the single-step mismatch breakpoint and
restarts immediately, so the core runs with the previous breakpoint contents: every second
step lands somewhere random, and a stale armed breakpoint can turn into a Prefetch Abort in
the firmware after resume (the demo firmware's abort handler then parks the core).

Fix: `debug/openocd-isb-before-restart.py` adds one `ISB` executed through the ITR in
`cortex_a_internal_restart()` before every restart. The prebuilt OpenOCD in the Releases
carries it; `debug/build-openocd.sh` applies it when building from source. Harmless on a
real APB-AP path.

### 3. Interrupts during single step

OpenOCD's `cortex_r4` target does not mask interrupts while stepping by default. With the
firmware's 1 kHz tick running, every `step`/`next` ended in `IRQ_Handler`. The config sets
`cortex_r4 maskisr on`. Ticks are lost while stepping, which is fine for debugging.

## The OpenOCD configuration, line by line

```
adapter driver dmem
dmem device /dev/mem
dmem base_address 0x1F000000
dmem max_aps 1
dmem emu_ap_list 0
dmem emu_base_address_range 0x1F000000 0x01000000
```
AP 0 is *emulated*: a MEM-AP transaction becomes a plain access to physical address
`emu_base + TAR`. With `emu_base = 0x1F000000` the target's `-dbgbase` is an offset into the
16 MB debug window. `dmem` strips bit 31 from TAR, so `-dbgbase 0x80810000` (OpenOCD expects
bit 31 set for an APB-AP base and warns otherwise) reaches `0x1F810000`.

```
transport select swd
source [find target/swj-dp.tcl]
swj_newdap rzv2h cpu -irlen 4
dap create rzv2h.dap -tap rzv2h.cpu
target create rzv2h.cr8_0 cortex_r4 -dap rzv2h.dap -ap-num 0 -dbgbase 0x80810000 -coreid 0
```
`dmem` is a "dapdirect" driver and is selected as `swd`, as the upstream TI configs do.

```
rzv2h.cr8_0 configure -event examine-end { cr8_unlock }   ;# DBGLAR + HDBGen, pitfall 1
rzv2h.cr8_0 configure -event gdb-detach { if {[rzv2h.cr8_0 curstate] eq "halted"} { resume } }
reset_config none                                          ;# remoteproc owns the cluster
bindto 127.0.0.1 ; gdb port 3333 ; telnet port 4444 ; tcl port disabled
init
rzv2h.cr8_0 cortex_r4 maskisr on                           ;# pitfall 3
```
`gdb-detach` resumes explicitly; the default left the core halted after `detach`. Both
Disconnect and Terminate in e² studio leave the core running.

## `r8dbg.py`: the whole mechanism in 200 lines

`debug/r8dbg.py` drives the same registers from Python with `mmap` on `/dev/mem`, no
OpenOCD:

| Command | What it does |
|---|---|
| `status` | `DSCR`, `OSLSR`, `PRSR`, `LSR` |
| `pcs N` | N samples of `DBGPCSR` (non-intrusive) |
| `halt` / `regs` | `DRCR.HaltReq`, then r0–r14, CPSR, PC via `MCR p14` into the DTR |
| `step N` | mismatch breakpoint on BRP0 with `INTDIS`, ISB through ITR, restart, wait for halt |
| `resume` | restore r0, clear ITREN, `DRCR.Restart` |

It refuses to run unless `CPG_LP_CR8_CTL3` bit 12 is set. It exists to show that the
debugger is nothing but register traffic; day-to-day use goes through OpenOCD.

## What works in e² studio, what does not

Works (standard CDT/GDB views): source breakpoints with conditions (all hardware; 6 per
core), Step Into/Over/Return, Variables, Expressions, Registers, Memory, Disassembly, call
stack. Line stepping is reliable with `maskisr on`.

Does not work through this path: Renesas views that need the E2/J-Link back end (IO
Registers, Smart Manual linkage, the ETM trace window). The CR8 does have ETMs and a 16 KB
ETF in the CST; driving them from Linux has not been tried.

## Core1

Core1's debug unit is at `0x1F81_2000` and is in `cr8-dmem.cfg` as the second target
`rzv2h.cr8_1` (gdb port 3334, same unlock / HDBGen / detach handlers, `maskisr on`). Verified
2026-11-05 on the EVK with `cr8_core1_demo.elf` on core1 and the demo on core0:

* the core1 debug registers answer as soon as the cluster is up, even while core1 is still
  held by remoteproc (`offline`): `DBGDIDR 0x3513A003`, `DBGAUTHSTATUS 0xF0`, lock engaged;
* `r8dbg.py --core 1` halt / step / resume works, and core0's tick keeps running while core1
  is halted (the halt is per core);
* gdb on port 3334: hardware breakpoint in `r8_blackbox_pump`, `next`, detach resumes; a gdb
  session on port 3333 afterwards still works; both black boxes report no fault.

Two gdb clients at once (one per port) work as well: verified from a Windows host with
e² studio's `arm-none-eabi-gdb.exe`, core1 held at a breakpoint for 8 s while core0's tick
kept counting, then both halted, then both resumed on detach (see
[windows-host.md](windows-host.md), "Two cores at once").

Two things learned the hard way while doing this:

* In an event handler use `targets rzv2h.cr8_1; resume`. `rzv2h.cr8_1 resume` is not a
  command; with that typo the gdb-detach handler failed and the core stayed halted.
* Never kill OpenOCD while a core is halted. Both cores were left halted, the next OpenOCD
  instance failed to examine one of them and a blind `resume` restarted them from stale state:
  black box `fault_type = 5` (undefined instruction) on both. The launchers now resume every
  target and `shutdown` through the telnet port before any `pkill`. Recovery is
  `restart-r8-pair.sh` (both cores down, core0, core1).

## CM33

Not reachable by this method. The hardware manual puts the CM33 debug components (ITM, DWT,
FPB, SCS, its ETM and CTI) in the CM33's own address space, reachable only through the DAP's
AHB-AP (port 2), while only the CoreSight, CA55 and CR8 areas are "accessible via the system
bus and APB-AP". The CST ROM table read from Linux confirms it: entries for the CST
components, the CA55 and the CR8, none for the CM33. Debugging the CM33 from the A55 would
need a different path (its black box in DDR still works, as before).

## While the core is halted

GPT PWM outputs hold their last duty cycle (the timer is hardware; this is also why
emergency-stop code must zero the duty before anything else), the firmware tick and black-box
heartbeat stop, and rpmsg clients on the A55 time out. All of this is expected and is the
visible proof that the core is really stopped.
