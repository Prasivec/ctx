# Bash completion for ctx (optional standalone loader)
# Installed to ~/.local/share/ctx/completions/ctx.bash
# Usually loaded automatically when sourcing shell/ctx.sh

# shellcheck shell=bash

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

complete -F _ctx_complete ctx 2>/dev/null || true
