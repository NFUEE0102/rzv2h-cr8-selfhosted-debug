#!/bin/sh
# Manual tunnel (cr8-debug.sh opens its own): localhost:3333 -> OpenOCD gdb port on the EVK.
# Start OpenOCD on the EVK first:  sudo ~/r8ocd/r8ocd.sh
EVK=${EVK:-@EVK@}
exec ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -L 3333:127.0.0.1:3333 "$EVK"
