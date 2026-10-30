# Sourced by agent-status.tmux. No polling or status-time shell commands.

# Literal replacement, including tokens containing shell/regex metacharacters.
agent_remove_token() {
    agent_rest=$1
    agent_token=$2
    agent_result=
    while :; do
        case "$agent_rest" in
            *"$agent_token"*)
                agent_result=$agent_result${agent_rest%%"$agent_token"*}
                agent_rest=${agent_rest#*"$agent_token"}
                ;;
            *) printf '%s' "$agent_result$agent_rest"; return ;;
        esac
    done
}

agent_apply_preset() {
    agent_preset_mode=$1
    agent_open='#{E:@agent-status-internal-preset-window-open}'
    agent_close='#{E:@agent-status-internal-preset-window-close}'
    agent_icon='#{E:@agent-status-internal-preset-window-icon}'
    agent_other='#{E:@agent-status-internal-preset-other}'

    # Do not pretend to integrate into a completely custom status layout.
    if [ "$agent_preset_mode" = compact ]; then
        agent_layout=$(agent_tmux show-options -gqv 'status-format[0]')
        case "$agent_layout" in
            *window-status-format*window-status-current-format*status-right*) ;;
            *)
                agent_warn 'custom status-format: use preset none and place the public formats manually.'
                return
                ;;
        esac
    fi

    for agent_option in window-status-format window-status-current-format status-right; do
        agent_original=$(agent_tmux show-options -gqv "$agent_option")
        agent_clean=$agent_original
        for agent_marker in "$agent_open" "$agent_close" "$agent_icon" "$agent_other"; do
            agent_clean=$(agent_remove_token "$agent_clean" "$agent_marker")
        done
        case "$agent_clean" in
            *'@agent-status-internal-preset-'*)
                agent_warn "edited preset token in $agent_option; preserve this value and remove the damaged token manually."
                continue
                ;;
        esac
        agent_new=$agent_clean
        if [ "$agent_preset_mode" = compact ]; then
            if [ "$agent_option" = status-right ]; then
                case "$agent_new" in
                    *'#{E:@agent-status-other}'*|*'#{T:@agent-status-other}'*) ;;
                    *) agent_new=$agent_new$agent_other ;;
                esac
            else
                case "$agent_new" in
                    *'#{E:@agent-status-window}'*|*'#{T:@agent-status-window}'*) ;;
                    *) agent_new=$agent_new$agent_icon ;;
                esac
                agent_new=$agent_open$agent_new$agent_close
            fi
        fi
        if [ "$agent_new" != "$agent_original" ]; then
            agent_tmux set-option -g "$agent_option" "$agent_new"
        fi
    done
}
