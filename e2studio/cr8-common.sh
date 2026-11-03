# shellcheck shell=bash
# Shared pieces for cr8-debug.sh / cr8-redeploy.sh: configuration file, one-password
# SSH session (OpenSSH ControlMaster, no keys and no sshpass needed), sudo on the EVK.
#
# Config: ~/.config/cr8-debug.conf (created interactively on first run)
#   EVK_HOST=192.168.1.177        EVK IP or hostname            (ci:allow-ip example)
#   EVK_USER=ubuntu               login user (needs sudo)
#   EVK_PASS=                     optional; empty = ask once per session. Also used for sudo.
#   FW=cr8_demo.elf               firmware file name in /lib/firmware on the EVK
#   PROJECT_DIR=...               e2 studio project (firmware/build/core0-demo of this repo)
#   E2S=...                       e2 studio executable
#   WS=...                        e2 studio workspace
#   TOOLS_DIR=...                 <repo>/firmware/tools (patch-elf-phdr.py)

CONF=${CR8_CONF:-$HOME/.config/cr8-debug.conf}
PORT=3333
OCD_DIR=/home/${EVK_USER:-ubuntu}/r8ocd      # fixed below once EVK_USER is known

say()  { printf '\033[1;36m[%s]\033[0m %s\n' "${TAG:-cr8}" "$*"; }
warn() { printf '\033[1;33m[%s] %s\033[0m\n' "${TAG:-cr8}" "$*"; }
fail() { printf '\033[1;31m[%s] %s\033[0m\n' "${TAG:-cr8}" "$*"; read -r -p "Enter to close..." _; exit 1; }

ask() {  # ask VAR "prompt" "default"
    local v=$1 p=$2 d=$3 a
    read -r -p "$p [$d]: " a
    printf -v "$v" '%s' "${a:-$d}"
}

load_config() {
    if [ ! -f "$CONF" ]; then
        say "No config yet ($CONF). A few questions:"
        ask EVK_HOST "EVK IP address" "192.168.1.177"   # ci:allow-ip default only
        ask EVK_USER "EVK user" "ubuntu"
        local remember
        read -r -s -p "EVK password (also used for sudo on the EVK): " EVK_PASS; echo
        ask remember "Remember the password in $CONF (file mode 600)? [y/N]" "N"
        local repo; repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
        local e2s_default; e2s_default=$(ls -d "$HOME"/rzv-tools/e2studio/eclipse/e2studio /opt/renesas/e2studio/eclipse/e2studio 2>/dev/null | head -1)
        ask E2S "e2 studio executable" "${e2s_default:-$HOME/rzv-tools/e2studio/eclipse/e2studio}"
        ask WS "e2 studio workspace" "$HOME/cr8dbg-workspace"
        ask PROJECT_DIR "e2 studio project directory" "$repo/firmware/build/core0-demo"
        ask FW "firmware file name on the EVK" "cr8_demo.elf"
        mkdir -p "$(dirname "$CONF")"
        {
            echo "EVK_HOST=$EVK_HOST"; echo "EVK_USER=$EVK_USER"
            case $remember in y|Y) echo "EVK_PASS=$EVK_PASS";; *) echo "EVK_PASS=";; esac
            echo "FW=$FW"; echo "PROJECT_DIR=$PROJECT_DIR"; echo "E2S=$E2S"; echo "WS=$WS"
            echo "TOOLS_DIR=$repo/firmware/tools"
        } > "$CONF"
        chmod 600 "$CONF"
        say "saved $CONF (edit it any time; delete it to be asked again)"
    fi
    # shellcheck disable=SC1090
    . "$CONF"
    : "${EVK_HOST:?EVK_HOST missing in $CONF}" "${EVK_USER:=ubuntu}" "${FW:=cr8_demo.elf}"
    EVK="$EVK_USER@$EVK_HOST"
    OCD_DIR=/home/$EVK_USER/r8ocd
    CTL="$HOME/.ssh/cr8-%r@%h-%p"
    mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
    SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$CTL" -o ControlPersist=900
              -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)
}

# Open (or reuse) the master connection. The first time this asks for the password in the
# terminal; every ssh/scp below rides on the same connection without asking again.
ssh_connect() {
    if ! ssh "${SSH_OPTS[@]}" -O check "$EVK" 2>/dev/null; then
        say "connecting to $EVK (password prompt comes from ssh; nothing is stored)"
        ssh "${SSH_OPTS[@]}" -o BatchMode=no "$EVK" true || fail "cannot log in to $EVK"
    fi
    ensure_sudo_pass
}

# Ask for the EVK sudo password once per run, on the terminal itself, so the prompt can never
# be swallowed by a redirected evk_sudo call (that hung --stop once). Kept in memory only.
ensure_sudo_pass() {
    [ -n "${EVK_PASS:-}" ] && return 0
    if [ -r /dev/tty ]; then
        read -r -s -p "sudo password for $EVK_USER on the EVK: " EVK_PASS < /dev/tty 2> /dev/tty
        echo > /dev/tty
    else
        read -r -s -p "sudo password for $EVK_USER on the EVK: " EVK_PASS; echo
    fi
}
ssh_close() { ssh "${SSH_OPTS[@]}" -O exit "$EVK" 2>/dev/null || true; }
evk()       { ssh "${SSH_OPTS[@]}" "$EVK" "$@"; }
evk_cp()    { scp -q -o ControlMaster=auto -o "ControlPath=$CTL" "$1" "$EVK:$2"; }

# sudo on the EVK. Password: config, else asked once per run (kept in memory only).
evk_sudo() {
    ensure_sudo_pass
    ssh "${SSH_OPTS[@]}" "$EVK" "printf '%s\n' '$EVK_PASS' | sudo -S -p '' $*"
}

evk_state() { evk cat /sys/class/remoteproc/remoteproc1/state 2>/dev/null; }
evk_ocd_running() { evk pgrep openocd >/dev/null 2>&1; }

evk_ocd_start() {
    evk_sudo "sh -c ': > $OCD_DIR/ocd.log; cd $OCD_DIR && nohup ./r8ocd.sh >> ocd.log 2>&1 &'"
    for _ in $(seq 1 25); do
        evk "grep -q 'Listening on port $PORT' $OCD_DIR/ocd.log" 2>/dev/null && break
        evk "grep -qE 'Refusing|Error|not found' $OCD_DIR/ocd.log" 2>/dev/null && {
            evk "grep -v '^Debug' $OCD_DIR/ocd.log | tail -5"; fail "OpenOCD failed to start"; }
        sleep 1
    done
    evk "grep -q 'Listening on port $PORT' $OCD_DIR/ocd.log && pgrep openocd >/dev/null" || fail "OpenOCD did not start listening"
    evk "ss -ltn 2>/dev/null | grep -q ':$PORT '" || fail "nothing listening on :$PORT on the EVK"
}

evk_ocd_stop() {
    evk_sudo "pkill -TERM openocd" >/dev/null 2>&1
    for _ in 1 2 3 4 5; do evk_ocd_running || return 0; sleep 1; done
    evk_sudo "pkill -KILL openocd" >/dev/null 2>&1; sleep 1
    evk_ocd_running && return 1 || return 0
}

tunnel_up()   { ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT "; }
tunnel_open() {
    tunnel_up && return 0
    ssh "${SSH_OPTS[@]}" -N -f -o ExitOnForwardFailure=yes -L "$PORT:127.0.0.1:$PORT" "$EVK" \
        || fail "tunnel failed (port $PORT busy? another cr8-debug still open?)"
    local _i; for _i in $(seq 1 10); do tunnel_up && return 0; sleep 0.5; done
    fail "tunnel did not come up"
}
tunnel_close() { pkill -f "[s]sh .*-L $PORT:127.0.0.1:$PORT $EVK" 2>/dev/null || true; }
