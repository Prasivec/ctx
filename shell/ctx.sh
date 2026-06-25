# ctx shell integration for bash
# Source this file from ~/.bashrc:
#   source ~/.local/share/ctx/shell/ctx.sh

# shellcheck shell=bash

_ctxctl() {
    if [[ -n "${CTXCTL_BIN:-}" && -x "${CTXCTL_BIN}" ]]; then
        printf '%s\n' "${CTXCTL_BIN}"
        return 0
    fi
    local _prefix="${CTX_PREFIX:-$HOME/.local}"
    if [[ -x "${_prefix}/bin/ctxctl" ]]; then
        printf '%s\n' "${_prefix}/bin/ctxctl"
        return 0
    fi
    command -v ctxctl
}

_ctx_unload_vault() {
    local _bin="$1"
    local _vault="$2"
    local _key

    # Prefer the tracked set of currently loaded keys so unloading works even
    # if the vault file was removed (ctx delete) or edited. Fall back to the
    # vault's on-disk keys for shells started before CTX_LOADED_KEYS existed.
    if [[ -n "${CTX_LOADED_KEYS:-}" ]]; then
        # CTX_LOADED_KEYS is a space-separated list of validated identifiers;
        # word-splitting is intentional here.
        # shellcheck disable=SC2086
        for _key in ${CTX_LOADED_KEYS}; do
            [[ -n "$_key" ]] || continue
            unset "$_key"
        done
    elif [[ -n "$_vault" ]]; then
        while IFS= read -r _key; do
            [[ -n "$_key" ]] || continue
            unset "$_key"
        done < <("$_bin" _shell keys-for "$_vault" 2>/dev/null)
    fi

    unset CTX_LOADED_KEYS
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
        echo "error: ctxctl not found in PATH. Run install.sh first." >&2
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
                    echo "usage: ctx load <vault>" >&2
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
                echo "error: No vault loaded in this terminal." >&2
                return 1
            fi
            _ctx_unload_vault "$_ctxctl_bin" "$CTX_LOADED_VAULT"
            unset CTX_ACTIVE_VAULT
            return 0
            ;;
        set)
            if [[ $# -lt 2 ]]; then
                echo "usage: ctx set <key> <value>" >&2
                return 1
            fi
            "$_ctxctl_bin" set "$@" || return $?
            if [[ -z "${CTX_ACTIVE_VAULT:-}" ]]; then
                echo "error: No active vault in this terminal. Run 'ctx load <vault>' first." >&2
                return 1
            fi
            _ctx_apply_vault "$_ctxctl_bin" "$CTX_ACTIVE_VAULT"
            return $?
            ;;
        unset)
            "$_ctxctl_bin" unset "$@" || return $?
            if [[ -n "${CTX_ACTIVE_VAULT:-}" ]]; then
                _ctx_apply_vault "$_ctxctl_bin" "$CTX_ACTIVE_VAULT"
                return $?
            fi
            return 0
            ;;
        clear)
            "$_ctxctl_bin" clear "$@" || return $?
            if [[ -n "${CTX_ACTIVE_VAULT:-}" ]]; then
                _ctx_apply_vault "$_ctxctl_bin" "$CTX_ACTIVE_VAULT"
                return $?
            fi
            return 0
            ;;
        current)
            if [[ -n "${CTX_ACTIVE_VAULT:-}" ]]; then
                printf '%s\n' "$CTX_ACTIVE_VAULT"
                return 0
            fi
            "$_ctxctl_bin" current
            return $?
            ;;
        delete)
            if [[ $# -lt 1 ]]; then
                echo "usage: ctx delete <vault> [--force]" >&2
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
                echo "usage: ctx rename <old> <new>" >&2
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

# bash-completion's _init_completion populates cur/prev/words/cword, and the
# COMPREPLY=( $(compgen ...) ) idiom relies on intentional word-splitting.
# shellcheck disable=SC2207,SC2034
_ctx_complete() {
    local cur prev words cword
    _init_completion || return 0

    local commands="create load unload current list set get unset show clear edit path delete rename duplicate help"
    local subcmd=""
    if [[ ${#words[@]} -ge 2 ]]; then
        subcmd="${words[1]}"
    fi

    case "$subcmd" in
        load|delete|duplicate)
            if [[ $cword -eq 2 ]]; then
                local vaults
                vaults="$("$(command -v ctxctl 2>/dev/null)" list 2>/dev/null)" || vaults=""
                COMPREPLY=($(compgen -W "$vaults" -- "$cur"))
            fi
            ;;
        rename)
            if [[ $cword -eq 2 ]]; then
                local vaults
                vaults="$("$(command -v ctxctl 2>/dev/null)" list 2>/dev/null)" || vaults=""
                COMPREPLY=($(compgen -W "$vaults" -- "$cur"))
            fi
            ;;
        get|unset)
            if [[ $cword -eq 2 && -n "${CTX_ACTIVE_VAULT:-}" ]]; then
                local keys
                keys="$("$(command -v ctxctl 2>/dev/null)" _shell keys 2>/dev/null)" || keys=""
                COMPREPLY=($(compgen -W "$keys" -- "$cur"))
            fi
            ;;
        set)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=($(compgen -W "ip domain user pass token host dc url port rhost lhost target" -- "$cur"))
            fi
            ;;
        ""|help)
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
            ;;
        *)
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
            ;;
    esac
}

if [[ -n "${BASH_VERSION:-}" ]]; then
    complete -F _ctx_complete ctx 2>/dev/null || true
fi
