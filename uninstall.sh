#!/usr/bin/env bash
# uninstall.sh - Remove ctx installation (optionally vault data)

set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/ctx"
MAN_PAGE="$PREFIX/share/man/man1/ctx.1"

# Resolve the config directory consistently with the Python backend, which
# honors XDG_CONFIG_HOME. Treat an unset OR empty value as "use the default".
if [ -n "${XDG_CONFIG_HOME:-}" ]; then
    CONFIG_BASE="$XDG_CONFIG_HOME"
else
    CONFIG_BASE="$HOME/.config"
fi
CONFIG_DIR="$CONFIG_BASE/ctx"

CTX_RC_BEGIN="# >>> ctx shell integration >>>"
CTX_RC_END="# <<< ctx shell integration <<<"

info() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }

confirm() {
    local prompt="$1"
    local answer
    read -r -p "$prompt [y/N]: " answer || answer=""
    case "$answer" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

remove_shell_rc_block() {
    local rc
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        [[ -f "$rc" ]] || continue
        if ! grep -qF "$CTX_RC_BEGIN" "$rc" 2>/dev/null; then
            continue
        fi
        python3 - "$rc" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
begin = "# >>> ctx shell integration >>>"
end = "# <<< ctx shell integration <<<"
start = text.find(begin)
while start != -1:
    stop = text.find(end, start)
    if stop == -1:
        break
    stop = text.find("\n", stop)
    if stop == -1:
        text = text[:start]
    else:
        text = text[:start] + text[stop + 1 :]
    start = text.find(begin)
text = text.rstrip("\n") + "\n" if text.strip() else text
path.write_text(text, encoding="utf-8")
PY
        info "Removed shell integration block from $rc"
    done
}

info "Uninstalling ctx..."

# Remove Python package
if command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -q '\bctx\b'; then
    info "Removing ctxctl via pipx..."
    pipx uninstall ctx || true
elif command -v python3 >/dev/null 2>&1; then
    info "Removing ctxctl via pip..."
    python3 -m pip uninstall -y ctx 2>/dev/null || true
fi

# Remove installed files
rm -f "$BIN_DIR/ctx"
if [[ -L "$BIN_DIR/ctxctl" ]]; then
    rm -f "$BIN_DIR/ctxctl"
fi
rm -rf "$SHARE_DIR"
rm -f "$MAN_PAGE"

if command -v mandb >/dev/null 2>&1; then
    mandb -q "$PREFIX/share/man" 2>/dev/null || true
fi

remove_shell_rc_block

# Optionally remove vault data
if [[ -d "$CONFIG_DIR" ]]; then
    info ""
    if confirm "Delete vault data in $CONFIG_DIR?"; then
        rm -rf "$CONFIG_DIR"
        info "Removed $CONFIG_DIR"
    else
        info "Kept vault data at $CONFIG_DIR"
    fi
fi

info ""
info "Uninstall complete."
info "Open a new shell or run 'hash -r' if commands are still cached."
