#compdef ctx
# Zsh completion for ctx (optional standalone loader)
# Installed to ~/.local/share/ctx/completions/ctx.zsh

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

compdef _ctx_complete ctx
