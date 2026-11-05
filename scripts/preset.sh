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

# The text before the first window label (#I or #W) in a format.
agent_label_prefix() {
    agent_label=$1
    for agent_name in '#I' '#W' '#{window_index}' '#{window_name}'; do
        agent_before=${1%%"$agent_name"*}
        if [ "${#agent_before}" -lt "${#agent_label}" ]; then
            agent_label=$agent_before
        fi
    done
    printf '%s' "$agent_label"
}

# The bg or fg color the last style in $1 sets, if it is a literal color or
# an option reference such as #{@thm_blue}. Reversed styles draw separators
# from the surrounding colors, so they do not name the tab's colors.
agent_segment_color() {
    agent_rest=$1
    agent_color=
    while :; do
        case "$agent_rest" in *'#['*) ;; *) break ;; esac
        agent_rest=${agent_rest#*'#['}
        agent_style=${agent_rest%%']'*}
        case ",$agent_style," in *,reverse,*) continue ;; esac
        agent_items=$agent_style,
        while [ -n "$agent_items" ]; do
            agent_item=${agent_items%%[, ]*}
            agent_items=${agent_items#*[, ]}
            case "$agent_item" in "$2="*) agent_color=${agent_item#"$2="} ;; esac
        done
    done
    case "$agent_color" in
        '#{@'*'}')
            case "${agent_color#'#{@'}" in *[!A-Za-z0-9_-]'}'|*'{'*) return ;; esac
            printf '%s' "$agent_color"
            ;;
        ''|*[!#A-Za-z0-9]*|default|terminal) ;;
        *) printf '%s' "$agent_color" ;;
    esac
}

# Route every use of one tab color through the accent. A background color is
# also a separator's foreground, so both keys follow it.
agent_tint_color() {
    agent_tinted=$1
    for agent_end in ',' ']' ' '; do
        if [ "$3" = bg ]; then
            for agent_key in bg fg; do
                agent_tinted=$(agent_replace_token "$agent_tinted" \
                    "$agent_key=$2$agent_end" \
                    "$agent_key=$agent_tint_bg$2$agent_tint_end$agent_end")
            done
        else
            agent_tinted=$(agent_replace_token "$agent_tinted" \
                "fg=$2$agent_end" "fg=$agent_tint_fg$2$agent_tint_end$agent_end")
        fi
    done
    printf '%s' "$agent_tinted"
}

# Themes that draw tabs with inline colors override the wrapping accent, so
# route the tab's own colors (including separator glyphs) through the accent:
# the colors where the label starts, and those where the icon sits.
agent_tint() {
    agent_tinted=$1
    agent_prefixes=$(agent_label_prefix "$1")
    case "$1" in
        *"$agent_icon") agent_at_icon= ;;  # Appended after the tab: skip.
        *"$agent_icon"*) agent_at_icon=${1%%"$agent_icon"*} ;;
        *) agent_at_icon= ;;
    esac
    agent_bgs=
    agent_fgs=
    for agent_prefix in "$agent_prefixes" "$agent_at_icon"; do
        [ -n "$agent_prefix" ] || continue
        agent_bgs="$agent_bgs $(agent_segment_color "$agent_prefix" bg)"
        agent_fgs="$agent_fgs $(agent_segment_color "$agent_prefix" fg)"
    done
    agent_done=' '
    for agent_bg in $agent_bgs; do
        case "$agent_done" in *" $agent_bg "*) continue ;; esac
        agent_tinted=$(agent_tint_color "$agent_tinted" "$agent_bg" bg)
        agent_done="$agent_done$agent_bg "
    done
    for agent_fg in $agent_fgs; do
        case "$agent_done" in *" $agent_fg "*) continue ;; esac
        agent_tinted=$(agent_tint_color "$agent_tinted" "$agent_fg" fg)
        agent_done="$agent_done$agent_fg "
    done
    printf '%s' "$agent_tinted"
}

# Pad before the label when nothing separates it from the tab's edge, so the
# accent does not start right at the first character. Only a label outside
# any #{...} is padded.
agent_lead_pad() {
    agent_prefix=$1
    for agent_name in '#I' '#W' '#{window_index}' '#{window_name}'; do
        agent_before=${1%%"$agent_name"*}
        if [ "${#agent_before}" -lt "${#agent_prefix}" ]; then
            agent_prefix=$agent_before
        fi
    done
    agent_popens=$(printf '%s' "$agent_prefix" | tr -cd '{' | wc -c)
    agent_pcloses=$(printf '%s' "$agent_prefix" | tr -cd '}' | wc -c)
    case "$agent_prefix" in
        *' ') printf '%s' "$1"; return ;;
    esac
    if [ $((agent_popens)) -ne $((agent_pcloses)) ]; then
        printf '%s' "$1"
        return
    fi
    printf '%s' "$agent_prefix$agent_icon_pad${1#"$agent_prefix"}"
}

# The start of the #{...} group that ends $1, or nothing if $1 does not end
# in one. Byte-based so the shell can split the string with it.
agent_last_group_prefix() {
    AGENT_TEXT=$1 LC_ALL=C awk 'BEGIN {
        s = ENVIRON["AGENT_TEXT"]; depth = 0
        if (substr(s, length(s), 1) != "}") exit
        for (i = length(s); i > 1; i--) {
            c = substr(s, i, 1)
            if (c == "}") depth++
            else if (c == "{" && --depth == 0) {
                if (substr(s, i - 1, 1) == "#") printf "%s", substr(s, 1, i - 2)
                exit
            }
        }
    }'
}

# Put the icon inside the tab: after the label and the tab's content, before
# its trailing padding, closing styles and separators. Otherwise append it.
agent_place_icon() {
    agent_head=$1
    agent_tail=
    while :; do
        # A trailing style followed only by separator glyphs or spaces closes
        # the tab. A style followed by text or formats starts more content.
        case "$agent_head" in
            *'#['*)
                agent_before=${agent_head%'#['*}
                agent_segment=${agent_head#"$agent_before"}
                case "$agent_segment" in *']'*) ;; *) break ;; esac
                case "${agent_segment#*']'}" in *[A-Za-z0-9#{}]*) ;; *)
                    agent_head=$agent_before
                    agent_tail=$agent_segment$agent_tail
                    continue
                    ;;
                esac
                ;;
        esac
        # A trailing conditional that switches styles, such as one choosing
        # the separator's background, also closes the tab.
        agent_before=$(agent_last_group_prefix "$agent_head")
        agent_segment=${agent_head#"$agent_before"}
        case "$agent_segment" in
            '#{'*'#['*)
                agent_head=$agent_before
                agent_tail=$agent_segment$agent_tail
                continue
                ;;
        esac
        break
    done
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
    agent_head=$(agent_lead_pad "$agent_head")
    # tmux's default formats end in a flags-or-space conditional: keep the
    # flags before the icon and pad after it, inside the tab.
    case "$agent_head" in
        *"$agent_default_flags")
            printf '%s' "${agent_head%"$agent_default_flags"}$agent_flags$agent_icon$agent_flags_pad$agent_tail"
            return
            ;;
    esac
    agent_pad=
    while :; do
        case "$agent_head" in
            *' ') agent_head=${agent_head% }; agent_pad=" $agent_pad" ;;
            *) break ;;
        esac
    done
    # Without padding of its own, the tab would end right at the icon.
    [ -n "$agent_pad" ] || agent_pad=$agent_icon_pad
    printf '%s' "$agent_head$agent_icon$agent_pad$agent_tail"
}

agent_apply_preset() {
    agent_preset_mode=$1
    agent_open='#{E:@agent-status-internal-preset-window-open}'
    agent_close='#{E:@agent-status-internal-preset-window-close}'
    agent_icon='#{E:@agent-status-internal-preset-window-icon}'
    agent_other='#{E:@agent-status-internal-preset-other}'
    agent_icon_pad='#{E:@agent-status-internal-preset-window-pad}'
    agent_flags='#{E:@agent-status-internal-preset-window-flags}'
    agent_flags_pad='#{E:@agent-status-internal-preset-window-flags-pad}'
    agent_default_flags='#{?window_flags,#{window_flags}, }'
    # Each tinted color picks the bell, stale, or running accent, else its own.
    agent_tint_bg='#{?#{E:@agent-status-internal-preset-bell-bg},#{@agent-status-internal-bell-bg},#{?#{E:@agent-status-internal-preset-stale-bg},#{@agent-status-internal-stale-bg},#{?#{E:@agent-status-internal-preset-running-bg},#{@agent-status-internal-running-bg},'
    agent_tint_fg='#{?#{E:@agent-status-internal-preset-bell-fg},#{@agent-status-internal-bell-fg},#{?#{E:@agent-status-internal-preset-stale-fg},#{@agent-status-internal-stale-fg},#{?#{E:@agent-status-internal-preset-running-fg},#{@agent-status-internal-running-fg},'
    agent_tint_end='}}}#{@agent-status-internal-preset-tint-end}'
    # The tint before stale accents existed, so formats applied by an older
    # version still clean up.
    agent_legacy_tint_bg='#{?#{E:@agent-status-internal-preset-bell-bg},#{@agent-status-internal-bell-bg},#{?#{E:@agent-status-internal-preset-running-bg},#{@agent-status-internal-running-bg},'
    agent_legacy_tint_fg='#{?#{E:@agent-status-internal-preset-bell-fg},#{@agent-status-internal-bell-fg},#{?#{E:@agent-status-internal-preset-running-fg},#{@agent-status-internal-running-fg},'
    agent_legacy_tint_end='}}#{@agent-status-internal-preset-tint-end}'

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
        agent_clean=$(agent_replace_token "$agent_original" "$agent_flags" "$agent_default_flags")
        for agent_marker in "$agent_open" "$agent_close" "$agent_icon" "$agent_other" \
            "$agent_icon_pad" "$agent_flags_pad" \
            "$agent_tint_bg" "$agent_tint_fg" "$agent_tint_end" \
            "$agent_legacy_tint_bg" "$agent_legacy_tint_fg" "$agent_legacy_tint_end"; do
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
