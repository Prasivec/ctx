#!/usr/bin/env bash
# install.sh - Install ctx (ctxctl backend + shell integration)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/ctx"
COMPLETIONS_DIR="$SHARE_DIR/completions"
SHELL_DIR="$SHARE_DIR/shell"
MAN_DIR="$PREFIX/share/man/man1"

# Resolve the config directory consistently with the Python backend, which
# honors XDG_CONFIG_HOME. Treat an unset OR empty value as "use the default".
if [ -n "${XDG_CONFIG_HOME:-}" ]; then
    CONFIG_BASE="$XDG_CONFIG_HOME"
else
    CONFIG_BASE="$HOME/.config"
fi
CONFIG_DIR="$CONFIG_BASE/ctx"
VAULTS_DIR="$CONFIG_DIR/vaults"

CTX_RC_BEGIN="# >>> ctx shell integration >>>"
CTX_RC_END="# <<< ctx shell integration <<<"

info() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

python_user_bin() {
    python3 -c "import site, os; print(os.path.join(site.USER_BASE, 'bin'))" 2>/dev/null || echo "$BIN_DIR"
}

ensure_bin_dir() {
    mkdir -p "$BIN_DIR"
}

install_python_package() {
    ensure_bin_dir
    if command -v pipx >/dev/null 2>&1; then
        info "Installing ctxctl with pipx..."
        pipx install "$SCRIPT_DIR" --force
        if pipx ensurepath >/dev/null 2>&1; then
            info "Ensured pipx/user bin directory is on PATH (pipx ensurepath)."
        fi
    elif command -v python3 >/dev/null 2>&1; then
        info "Installing ctxctl with python3 -m pip --user..."
        python3 -m pip install --user "$SCRIPT_DIR"
        local user_bin
        user_bin="$(python_user_bin)"
        if [[ "$user_bin" != "$BIN_DIR" && -d "$user_bin" ]]; then
            info "Python user scripts directory: $user_bin"
        fi
    else
        die "python3 is required but not found."
    fi
}

install_launcher() {
    ensure_bin_dir
    install -m 0755 "$SCRIPT_DIR/bin/ctx" "$BIN_DIR/ctx"
    info "Installed ctx launcher to $BIN_DIR/ctx"
}

link_ctxctl_into_bin_dir() {
    if [[ -x "$BIN_DIR/ctxctl" ]]; then
        return 0
    fi
    local candidate=""
    if command -v ctxctl >/dev/null 2>&1; then
        candidate="$(command -v ctxctl)"
    else
        local user_bin
        user_bin="$(python_user_bin)"
        if [[ -x "$user_bin/ctxctl" ]]; then
            candidate="$user_bin/ctxctl"
        fi
    fi
    if [[ -n "$candidate" && "$candidate" != "$BIN_DIR/ctxctl" ]]; then
        ln -sf "$candidate" "$BIN_DIR/ctxctl"
        info "Linked ctxctl into $BIN_DIR/ctxctl"
    fi
}

verify_ctxctl() {
    if [[ -x "$BIN_DIR/ctxctl" ]]; then
        info "Backend installed: $BIN_DIR/ctxctl"
        return 0
    fi
    local user_bin
    user_bin="$(python_user_bin)"
    if [[ -x "$user_bin/ctxctl" && "$user_bin" != "$BIN_DIR" ]]; then
        warn "ctxctl is in $user_bin but not $BIN_DIR."
        warn "Add export PATH=\"$user_bin:\$PATH\" to your shell rc file."
        return 0
    fi
    if command -v ctxctl >/dev/null 2>&1; then
        info "Backend available: $(command -v ctxctl)"
        return 0
    fi
    warn "ctxctl not found in PATH yet. Open a new shell after install."
}

shell_rc_block() {
    cat <<EOF

$CTX_RC_BEGIN
# ctx - terminal context manager (https://github.com/)
export PATH="$BIN_DIR:\$PATH"
export CTX_PREFIX="$PREFIX"
export CTXCTL_BIN="$BIN_DIR/ctxctl"
if [ -n "\${BASH_VERSION:-}" ] && [ -f "$SHELL_DIR/ctx.sh" ]; then
  . "$SHELL_DIR/ctx.sh"
elif [ -n "\${ZSH_VERSION:-}" ] && [ -f "$SHELL_DIR/ctx.zsh" ]; then
  . "$SHELL_DIR/ctx.zsh"
fi
$CTX_RC_END
EOF
}

configure_shell_rc() {
    local rc configured=0
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [[ ! -f "$rc" ]]; then
            touch "$rc"
        fi
        if grep -qF "$CTX_RC_BEGIN" "$rc" 2>/dev/null; then
            info "Shell integration already present in $rc"
            configured=1
            continue
        fi
        shell_rc_block >>"$rc"
        info "Configured shell integration in $rc"
        configured=1
    done
    if [[ "$configured" -eq 0 ]]; then
        warn "Could not configure shell rc files automatically."
    fi
}

info "Installing ctx..."

install_python_package
install_launcher
link_ctxctl_into_bin_dir

# Install shell integration files
mkdir -p "$SHELL_DIR" "$COMPLETIONS_DIR" "$MAN_DIR"
install -m 0644 "$SCRIPT_DIR/shell/ctx.sh" "$SHELL_DIR/ctx.sh"
install -m 0644 "$SCRIPT_DIR/shell/ctx.zsh" "$SHELL_DIR/ctx.zsh"
install -m 0644 "$SCRIPT_DIR/completions/ctx.bash" "$COMPLETIONS_DIR/ctx.bash"
install -m 0644 "$SCRIPT_DIR/completions/ctx.zsh" "$COMPLETIONS_DIR/ctx.zsh"
install -m 0644 "$SCRIPT_DIR/man/ctx.1" "$MAN_DIR/ctx.1"

if command -v mandb >/dev/null 2>&1; then
    mandb -q "$PREFIX/share/man" 2>/dev/null || true
fi

# Create vault storage with secure permissions
mkdir -p "$VAULTS_DIR"
chmod 700 "$CONFIG_DIR"
chmod 700 "$VAULTS_DIR"

configure_shell_rc
verify_ctxctl

info ""
info "Installation complete."
info ""
info "Binaries: $BIN_DIR/ctx and $BIN_DIR/ctxctl"
info "Shell integration was added to ~/.bashrc and ~/.zshrc (if missing)."
info ""
info "Activate in this terminal:"
info "  source ~/.bashrc    # bash"
info "  source ~/.zshrc     # zsh"
info ""
info "Or open a new terminal, then:"
info "  ctx create mylab"
info "  ctx load mylab"
info "  ctx set ip 10.10.10.1"
info "  echo \$ip"
info ""
info "Vault data directory: $VAULTS_DIR"
info "Man page: man ctx"
