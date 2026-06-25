# ctx shell integration for zsh
# Source this file from ~/.zshrc:
#   source ~/.local/share/ctx/shell/ctx.zsh

_ctxctl() {
    if [[ -n "${CTXCTL_BIN:-}" && -x "${CTXCTL_BIN}" ]]; then
        print -r -- "${CTXCTL_BIN}"
        return 0
    fi
    local _prefix="${CTX_PREFIX:-$HOME/.local}"
    if [[ -x "${_prefix}/bin/ctxctl" ]]; then
        print -r -- "${_prefix}/bin/ctxctl"
        return 0
    fi
    command -v ctxctl
}

_ctx_unload_vault() {
    local _bin="$1"
    local _vault="$2"
    local _key

    [[ -n "$_vault" ]] || return 0

    while IFS= read -r _key; do
        [[ -n "$_key" ]] || continue
        unset "$_key"
    done < <("$_bin" _shell keys-for "$_vault" 2>/dev/null)

    if [[ "${CTX_LOADED_VAULT:-}" == "$_vault" ]]; then
        unset CTX_LOADED_VAULT
    fi
}

# Apply a vault to this shell transactionally.
#
# The backend parses the named vault as data and emits sanitized export/unset
# statements (it never sources the user-editable vault file). The full shell
# script is generated into a variable FIRST; it is only eval'd if backend
# generation succeeds. If the vault is malformed/unsafe, generation fails and
# the shell state is left untouched. The caller owns CTX_ACTIVE_VAULT and must
# only update it after this function returns success.
_ctx_apply_vault() {
    local _bin="$1"
    local _vault="$2"
    local _out
    _out="$("$_bin" _shell load "$_vault")" || return $?
    eval "$_out"
    return 0
}

ctx() {
    local _ctxctl_bin
    _ctxctl_bin="$(_ctxctl)" || {
        print -u2 "error: ctxctl not found in PATH. Run install.sh first."
        return 127
    }

    if [[ $# -eq 0 ]]; then
        "$_ctxctl_bin" --help
        return $?
    fi

    local cmd="$1"
    shift

    case "$cmd" in
        help|--help|-h)
            "$_ctxctl_bin" --help
            return $?
            ;;
        load)
            local _target
            if [[ $# -ge 1 ]]; then
                "$_ctxctl_bin" load "$1" || return $?
                _target="$1"
            else
                if [[ -z "${CTX_ACTIVE_VAULT:-}" ]]; then
                    print -u2 "usage: ctx load <vault>"
                    return 1
                fi
                "$_ctxctl_bin" load || return $?
                _target="${CTX_ACTIVE_VAULT}"
            fi
            # Only mutate shell state if the backend can safely generate the
            # exports. On failure, the previously loaded vault stays active and
            # CTX_ACTIVE_VAULT is not changed.
            _ctx_apply_vault "$_ctxctl_bin" "$_target" || return $?
            export CTX_ACTIVE_VAULT="$_target"
            return 0
            ;;
        unload)
            if [[ -z "${CTX_LOADED_VAULT:-}" ]]; then
                print -u2 "error: No vault loaded in this terminal."
                return 1
            fi
            _ctx_unload_vault "$_ctxctl_bin" "$CTX_LOADED_VAULT"
            unset CTX_ACTIVE_VAULT
            return 0
            ;;
        set)
            if [[ $# -lt 2 ]]; then
                print -u2 "usage: ctx set <key> <value>"
                return 1
            fi
            "$_ctxctl_bin" set "$@" || return $?
            if [[ -z "${CTX_ACTIVE_VAULT:-}" ]]; then
                print -u2 "error: No active vault in this terminal. Run 'ctx load <vault>' first."
                return 1
            fi
            _ctx_apply_vault "$_ctxctl_bin" "$CTX_ACTIVE_VAULT"
            return $?
            ;;
        current)
            if [[ -n "${CTX_ACTIVE_VAULT:-}" ]]; then
                print -r -- "$CTX_ACTIVE_VAULT"
                return 0
            fi
            "$_ctxctl_bin" current
            return $?
            ;;
        delete)
            if [[ $# -lt 1 ]]; then
                print -u2 "usage: ctx delete <vault> [--force]"
                return 1
            fi
            local _del_vault="$1"
            shift
            "$_ctxctl_bin" delete "$_del_vault" "$@" || return $?
            if [[ "${CTX_ACTIVE_VAULT:-}" == "$_del_vault" ]]; then
                if [[ -n "${CTX_LOADED_VAULT:-}" ]]; then
                    _ctx_unload_vault "$_ctxctl_bin" "$CTX_LOADED_VAULT"
                fi
                unset CTX_ACTIVE_VAULT
            elif [[ "${CTX_LOADED_VAULT:-}" == "$_del_vault" ]]; then
                _ctx_unload_vault "$_ctxctl_bin" "$_del_vault"
            fi
            return 0
            ;;
        rename)
            if [[ $# -lt 2 ]]; then
                print -u2 "usage: ctx rename <old> <new>"
                return 1
            fi
            local _old_vault="$1"
            local _new_vault="$2"
            shift 2
            "$_ctxctl_bin" rename "$_old_vault" "$_new_vault" "$@" || return $?
            if [[ "${CTX_ACTIVE_VAULT:-}" == "$_old_vault" ]]; then
                export CTX_ACTIVE_VAULT="$_new_vault"
            fi
            if [[ "${CTX_LOADED_VAULT:-}" == "$_old_vault" ]]; then
                export CTX_LOADED_VAULT="$_new_vault"
            fi
            return 0
            ;;
        *)
            "$_ctxctl_bin" "$cmd" "$@"
            return $?
            ;;
    esac
}

_ctx_complete() {
    local -a commands
    commands=(
        create load unload current list set get unset show clear edit path delete rename duplicate help
    )

    local curcontext="$curcontext" state line
    typeset -A opt_args

    _arguments -C \
        '1:command:->command' \
        '*::arg:->args'

    case $state in
        command)
            _describe -t commands 'ctx command' commands
            ;;
        args)
            case $words[1] in
                load|delete|duplicate)
                    if [[ $CURRENT -eq 2 ]]; then
                        local -a vaults
                        vaults=("${(@f)$("$(command -v ctxctl)" list 2>/dev/null)}")
                        _describe -t vaults 'vault' vaults
                    fi
                    ;;
                rename)
                    if [[ $CURRENT -eq 2 ]]; then
                        local -a vaults
                        vaults=("${(@f)$("$(command -v ctxctl)" list 2>/dev/null)}")
                        _describe -t vaults 'vault' vaults
                    fi
                    ;;
                get|unset)
                    if [[ $CURRENT -eq 2 && -n "${CTX_ACTIVE_VAULT:-}" ]]; then
                        local -a keys
                        keys=("${(@f)$("$(command -v ctxctl)" _shell keys 2>/dev/null)}")
                        _describe -t keys 'key' keys
                    fi
                    ;;
                set)
                    if [[ $CURRENT -eq 2 ]]; then
                        local -a common_keys
                        common_keys=(ip domain user pass token host dc url port rhost lhost target)
                        _describe -t keys 'key' common_keys
                    fi
                    ;;
            esac
            ;;
    esac
}

if [[ -n "${ZSH_VERSION:-}" ]]; then
    compdef _ctx_complete ctx 2>/dev/null || true
fi
