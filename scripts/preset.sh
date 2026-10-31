# Sourced by agent-status.tmux. No polling or status-time shell commands.

# Literal replacement, including tokens containing shell/regex metacharacters.
agent_replace_token() {
    agent_rest=$1
    agent_token=$2
    agent_with=$3
    agent_result=
    while :; do
        case "$agent_rest" in
            *"$agent_token"*)
                agent_result=$agent_result${agent_rest%%"$agent_token"*}$agent_with
                agent_rest=${agent_rest#*"$agent_token"}
                ;;
            *) printf '%s' "$agent_result$agent_rest"; return ;;
        esac
    done
}

agent_remove_token() { agent_replace_token "$1" "$2" ''; }

# The literal bg/fg color in effect where the tab label (#I or #W) starts.
agent_tab_color() {
    agent_label=$1
    for agent_name in '#I' '#W' '#{window_index}' '#{window_name}'; do
        agent_before=${1%%"$agent_name"*}
        if [ "${#agent_before}" -lt "${#agent_label}" ]; then
            agent_label=$agent_before
        fi
    done
    case "$agent_label" in *"$2="*) ;; *) return ;; esac
    agent_color=${agent_label##*"$2="}
    agent_color=${agent_color%%[], ]*}
    case "$agent_color" in
        ''|*[!#A-Za-z0-9]*|default|terminal) ;;
        *) printf '%s' "$agent_color" ;;
    esac
}

# Themes that draw tabs with inline colors override the wrapping accent, so
# route the tab's own colors (including separator glyphs) through the accent.
agent_tint() {
    agent_tinted=$1
    agent_bg=$(agent_tab_color "$1" bg)
    agent_fg=$(agent_tab_color "$1" fg)
    for agent_end in ',' ']' ' '; do
        if [ -n "$agent_bg" ]; then
            for agent_key in bg fg; do
                agent_tinted=$(agent_replace_token "$agent_tinted" \
                    "$agent_key=$agent_bg$agent_end" \
                    "$agent_key=$agent_tint_bg$agent_bg$agent_tint_end$agent_end")
            done
        fi
        if [ -n "$agent_fg" ] && [ "$agent_fg" != "$agent_bg" ]; then
            agent_tinted=$(agent_replace_token "$agent_tinted" \
                "fg=$agent_fg$agent_end" "fg=$agent_tint_fg$agent_fg$agent_tint_end$agent_end")
        fi
    done
    printf '%s' "$agent_tinted"
}

# Put the icon inside the tab, before its trailing padding and any closing
# style and separator that follow the label, outside any #{...}. Otherwise
# append it.
agent_place_icon() {
    case "$1" in
        *'#['*)
            agent_head=${1%'#['*}
            agent_tail=${1#"$agent_head"}
            ;;
        *) agent_head=$1; agent_tail= ;;
    esac
    agent_opens=$(printf '%s' "$agent_head" | tr -cd '{' | wc -c)
    agent_closes=$(printf '%s' "$agent_head" | tr -cd '}' | wc -c)
    case "$agent_head" in
        *'#I'*|*'#W'*|*'#{window_index}'*|*'#{window_name}'*) ;;
        *) printf '%s' "$1$agent_icon"; return ;;
    esac
    if [ $((agent_opens)) -ne $((agent_closes)) ]; then
        printf '%s' "$1$agent_icon"
        return
    fi
    agent_pad=
    while :; do
        case "$agent_head" in
            *' ') agent_head=${agent_head% }; agent_pad=" $agent_pad" ;;
            *) break ;;
        esac
    done
    printf '%s' "$agent_head$agent_icon$agent_pad$agent_tail"
}

agent_apply_preset() {
    agent_preset_mode=$1
    agent_open='#{E:@agent-status-internal-preset-window-open}'
    agent_close='#{E:@agent-status-internal-preset-window-close}'
    agent_icon='#{E:@agent-status-internal-preset-window-icon}'
    agent_other='#{E:@agent-status-internal-preset-other}'
    agent_tint_bg='#{?#{E:@agent-status-internal-preset-bell-bg},#{@agent-status-internal-bell-bg},#{?#{E:@agent-status-internal-preset-running-bg},#{@agent-status-internal-running-bg},'
    agent_tint_fg='#{?#{E:@agent-status-internal-preset-bell-fg},#{@agent-status-internal-bell-fg},#{?#{E:@agent-status-internal-preset-running-fg},#{@agent-status-internal-running-fg},'
    agent_tint_end='}}#{@agent-status-internal-preset-tint-end}'

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
        for agent_marker in "$agent_open" "$agent_close" "$agent_icon" "$agent_other" \
            "$agent_tint_bg" "$agent_tint_fg" "$agent_tint_end"; do
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
                    *) agent_new=$(agent_place_icon "$agent_new") ;;
                esac
                agent_new=$agent_open$(agent_tint "$agent_new")$agent_close
            fi
        fi
        if [ "$agent_new" != "$agent_original" ]; then
            agent_tmux set-option -g "$agent_option" "$agent_new"
        fi
    done
}
