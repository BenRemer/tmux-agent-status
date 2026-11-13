#!/bin/sh
# TPM entry point. Resolve configuration and install tmux formats and hooks.
set -eu

agent_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
agent_bin=${TMUX_BIN:-tmux}
agent_socket=
agent_uninstall=
agent_usage() {
    printf '%s\n' 'Usage: agent-status.tmux [--socket PATH] [--uninstall]' >&2
    exit 2
}
while [ "$#" -gt 0 ]; do
    case "$1" in
        --socket) [ "$#" -ge 2 ] || agent_usage; agent_socket=$2; shift 2 ;;
        --uninstall) agent_uninstall=1; shift ;;
        *) agent_usage ;;
    esac
done
if [ -z "$agent_socket" ] && [ -n "${TMUX-}" ]; then
    # The final two comma-separated fields are the server PID and session ID.
    agent_socket=${TMUX%,*}
    agent_socket=${agent_socket%,*}
fi
if [ -z "$agent_socket" ]; then
    printf '%s\n' 'tmux-agent-status: load with tmux run-shell, or specify --socket PATH.' >&2
    exit 2
fi

# -u: without a UTF-8 locale, tmux would return non-ASCII text (icons, title
# strings) as underscores, and the plugin would save that back.
agent_tmux() { "$agent_bin" -u -S "$agent_socket" "$@"; }
agent_warn() {
    printf 'tmux-agent-status: %s\n' "$*" >&2
    agent_tmux display-message "tmux-agent-status: $*" 2>/dev/null || :
}
agent_input() {
    if [ -n "$(agent_tmux show-options -gq "$1")" ]; then
        agent_tmux show-options -gqv "$1"
    else
        printf '%s' "$2"
    fi
}

# Check the running server rather than a possibly different client binary.
agent_version=$(agent_tmux display-message -p '#{version}')
agent_numeric=${agent_version#next-}
agent_major=${agent_numeric%%.*}
agent_minor=${agent_numeric#*.}
agent_minor=$(printf '%s' "$agent_minor" | sed 's/[^0-9].*$//')
case "$agent_major:$agent_minor" in
    *[!0-9:]*|:*|*:)
        agent_warn "tmux 3.4 or newer is required; server version is unavailable or unrecognized ($agent_version)."
        exit 1
        ;;
esac
if [ "$agent_major" -lt 3 ] ||
   { [ "$agent_major" -eq 3 ] && [ "$agent_minor" -lt 4 ]; }; then
    agent_warn 'tmux 3.4 or newer is required; no settings changed.'
    exit 1
fi

agent_hook='pane-title-changed[4721]'
agent_relay_token='#{E:@agent-status-internal-relay-title}'

# Remote relay, inner side: publish agent activity in the terminal title for
# an outer tmux to read. The user's own title settings are kept and restored.
agent_relay_start() {
    if [ "$(agent_tmux show-options -gv set-titles-string)" != "$agent_relay_token" ]; then
        agent_tmux set-option -g @agent-status-internal-relay-saved 1
        agent_tmux set-option -g @agent-status-internal-relay-saved-titles \
            "$(agent_tmux show-options -gv set-titles)"
        agent_tmux set-option -g @agent-status-internal-relay-fallback \
            "$(agent_tmux show-options -gv set-titles-string)"
    fi
    agent_tmux set-option -g set-titles on
    agent_tmux set-option -g set-titles-string "$agent_relay_token"
    # The title's timestamp only advances when tmux redraws the status line.
    agent_interval=$(agent_tmux show-options -gv status-interval)
    if [ "$agent_interval" -eq 0 ] || [ "$agent_interval" -gt 15 ]; then
        agent_warn "@agent-status-relay needs status-interval between 1 and 15 (it is $agent_interval); the outer tmux will show the relay as stale."
    fi
}
agent_relay_stop() {
    if [ "$(agent_tmux show-options -gv set-titles-string)" = "$agent_relay_token" ]; then
        if [ "$(agent_tmux show-options -gqv @agent-status-internal-relay-saved)" = 1 ]; then
            agent_tmux set-option -g set-titles \
                "$(agent_tmux show-options -gqv @agent-status-internal-relay-saved-titles)"
            agent_tmux set-option -g set-titles-string \
                "$(agent_tmux show-options -gqv @agent-status-internal-relay-fallback)"
        else
            agent_tmux set-option -gu set-titles
            agent_tmux set-option -gu set-titles-string
        fi
    fi
    for agent_name in saved saved-titles fallback; do
        agent_tmux set-option -gu "@agent-status-internal-relay-$agent_name"
    done
}

# Undo everything the plugin set on this server: preset tokens in the
# user's formats, the completion-bell hook, and every plugin option.
if [ -n "$agent_uninstall" ]; then
    # shellcheck source=scripts/preset.sh
    . "$agent_dir/scripts/preset.sh"
    agent_apply_preset none
    agent_relay_stop
    agent_tmux set-hook -gu "$agent_hook"
    agent_tmux show-options -g | sed -n 's/^\(@agent-status-[^ ]*\).*/\1/p' |
        while IFS= read -r agent_name; do
            agent_tmux set-option -gu "$agent_name"
        done
    agent_tmux list-panes -a -F '#{pane_id}' | while IFS= read -r agent_pane; do
        for agent_name in @agent-status-busy-command @agent-status-internal-title-busy; do
            agent_tmux set-option -pu -t "$agent_pane" "$agent_name" 2>/dev/null || :
        done
    done
    exit 0
fi

agent_mode=$(agent_input @agent-status-preset none)
case "$agent_mode" in
    none) agent_running_default=; agent_bell_default=; agent_stale_default= ;;
    compact)
        agent_running_default='bg=#30464b,fg=#cad3f5'
        agent_bell_default='bg=#eed49f,fg=#181926,bold'
        agent_stale_default='bg=#4b3036,fg=#f0c6c6'
        ;;
    *) agent_warn '@agent-status-preset must be none or compact'; exit 1 ;;
esac

# tmux cannot see the terminal's font. The Nerd Font bell matches the cog's
# size; terminals without a Nerd Font can choose the wider emoji bell.
agent_icons=$(agent_input @agent-status-icons nerd-font)
case "$agent_icons" in
    nerd-font) agent_running_glyph='⚙'; agent_bell_glyph=''; agent_stale_glyph='' ;;
    emoji) agent_running_glyph='⚙'; agent_bell_glyph='🔔'; agent_stale_glyph='⚠' ;;
    *) agent_warn '@agent-status-icons must be nerd-font or emoji'; exit 1 ;;
esac
agent_completion_bell=$(agent_input @agent-status-completion-bell on)
case "$agent_completion_bell" in
    on|off) ;;
    *) agent_warn '@agent-status-completion-bell must be on or off'; exit 1 ;;
esac
# Claude adapter: a follow-up turn a finished background task starts rings
# only if it ends at least this many seconds after the previous turn.
agent_followup_seconds=$(agent_input @agent-status-followup-bell-seconds 30)
# In the window tmux is showing, only a turn at least this long rings.
agent_viewed_seconds=$(agent_input @agent-status-viewed-bell-seconds 10)
for agent_value in "$agent_followup_seconds" "$agent_viewed_seconds"; do
    case "$agent_value" in
        ''|*[!0-9]*) agent_warn '@agent-status-followup-bell-seconds and @agent-status-viewed-bell-seconds must be whole numbers of seconds'; exit 1 ;;
    esac
done
agent_relay=$(agent_input @agent-status-relay off)
agent_relay_count=$(agent_input @agent-status-relay-count off)
for agent_value in "$agent_relay" "$agent_relay_count"; do
    case "$agent_value" in
        on|off) ;;
        *) agent_warn '@agent-status-relay and @agent-status-relay-count must be on or off'; exit 1 ;;
    esac
done
agent_running_icon=$(agent_input @agent-status-running-icon "$agent_running_glyph")
agent_bell_icon=$(agent_input @agent-status-bell-icon "$agent_bell_glyph")
agent_stale_icon=$(agent_input @agent-status-stale-icon "$agent_stale_glyph")
agent_relay_pattern=$(agent_input @agent-status-relay-command-pattern '^(ssh|mosh-client|et)$')
agent_command_pattern=$(agent_input @agent-status-command-pattern '^(codex|claude|agy)$')
agent_title_pattern=$(agent_input @agent-status-agent-title-pattern '^✳ ')
agent_busy_pattern=$(agent_input @agent-status-busy-title-pattern '^(⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏) ')
agent_running_style=$(agent_input @agent-status-running-style "$agent_running_default")
agent_bell_style=$(agent_input @agent-status-bell-style "$agent_bell_default")
agent_stale_style=$(agent_input @agent-status-stale-style "$agent_stale_default")

# Inputs are passed as individual arguments, never evaluated as shell code.
for agent_value in "$agent_running_icon" "$agent_bell_icon" "$agent_stale_icon" \
    "$agent_command_pattern" "$agent_title_pattern" "$agent_busy_pattern" \
    "$agent_relay_pattern" "$agent_running_style" "$agent_bell_style" "$agent_stale_style"; do
    case "$agent_value" in
        *'
'*) agent_warn 'icons, styles, and patterns must each be a single line'; exit 1 ;;
    esac
done
for agent_pattern in "$agent_command_pattern" "$agent_title_pattern" "$agent_busy_pattern" \
    "$agent_relay_pattern"; do
    agent_regex_result=0
    printf '' | grep -E -e "$agent_pattern" >/dev/null 2>&1 || agent_regex_result=$?
    if [ "$agent_regex_result" -gt 1 ]; then
        agent_warn 'invalid recognition regular expression; no settings changed.'
        exit 1
    fi
done

# A literal bg/fg color from a style, for tinting themes with inline colors.
agent_style_color() {
    agent_color=$(printf '%s\n' "$1" | tr ',' ' ' | tr ' ' '\n' | sed -n "s/^$2=//p" | tail -n 1)
    case "$agent_color" in
        *[!#A-Za-z0-9]*) ;;
        *) printf '%s' "$agent_color" ;;
    esac
}

# Resolved defaults never overwrite user input options.
agent_tmux set-option -g @agent-status-internal-followup-bell-seconds "$agent_followup_seconds"
agent_tmux set-option -g @agent-status-internal-viewed-bell-seconds "$agent_viewed_seconds"
agent_tmux set-option -g @agent-status-internal-running-icon "$agent_running_icon"
agent_tmux set-option -g @agent-status-internal-bell-icon "$agent_bell_icon"
agent_tmux set-option -g @agent-status-internal-stale-icon "$agent_stale_icon"
agent_tmux set-option -g @agent-status-internal-relay-pattern "$agent_relay_pattern"
agent_tmux set-option -g @agent-status-internal-relay-count "$agent_relay_count"
agent_tmux set-option -g @agent-status-internal-command-pattern "$agent_command_pattern"
agent_tmux set-option -g @agent-status-internal-title-pattern "$agent_title_pattern"
agent_tmux set-option -g @agent-status-internal-busy-pattern "$agent_busy_pattern"
agent_tmux set-option -g @agent-status-internal-running-style "$agent_running_style"
agent_tmux set-option -g @agent-status-internal-bell-style "$agent_bell_style"
agent_tmux set-option -g @agent-status-internal-stale-style "$agent_stale_style"
agent_tmux set-option -g @agent-status-internal-running-bg "$(agent_style_color "$agent_running_style" bg)"
agent_tmux set-option -g @agent-status-internal-running-fg "$(agent_style_color "$agent_running_style" fg)"
agent_tmux set-option -g @agent-status-internal-bell-bg "$(agent_style_color "$agent_bell_style" bg)"
agent_tmux set-option -g @agent-status-internal-bell-fg "$(agent_style_color "$agent_bell_style" fg)"
agent_tmux set-option -g @agent-status-internal-stale-bg "$(agent_style_color "$agent_stale_style" bg)"
agent_tmux set-option -g @agent-status-internal-stale-fg "$(agent_style_color "$agent_stale_style" fg)"
agent_tmux source-file "$agent_dir/agent-status.conf"
if [ "$agent_relay" = on ]; then
    agent_relay_start
else
    agent_relay_stop
fi

# Ring the pane's bell when a busy agent title turns idle, so title-reporting
# agents (Codex, agy) need no notification setup. tmux commands only; the
# shell runs once per completed turn, never per title frame. The marker holds
# the turn's start time and is set only once per turn: setting an option
# redraws every client. In the window you are viewing, only a turn of at least
# @agent-status-viewed-bell-seconds (default 10) rings, so a startup spinner does
# not flash the screen; a real turn still rings, and tmux passes that bell on
# to an outer tmux, which may be showing another tab. A marker left by an
# agent that exited is cleared without ringing.
if [ "$agent_completion_bell" = on ]; then
    agent_tmux set-hook -g "$agent_hook" "if-shell -F '#{&&:#{@agent-status-internal-busy-pattern},#{m/r:#{@agent-status-internal-busy-pattern},#{pane_title}}}' { if-shell -F '#{?#{@agent-status-internal-title-busy},0,#{E:@agent-status-internal-pane}}' { set-option -pF @agent-status-internal-title-busy '#{T:@agent-status-internal-now}' } } { if-shell -F '#{@agent-status-internal-title-busy}' { if-shell -F '#{E:@agent-status-internal-bell-due}' { run-shell -b \"printf '\\\\a' > '#{pane_tty}'\" } ; set-option -pu @agent-status-internal-title-busy } }"
else
    agent_tmux set-hook -gu "$agent_hook"
    # A turn that finishes while the hook is disabled must not ring after
    # the hook is enabled again. Keep adapter activity markers intact.
    agent_tmux list-panes -a -F '#{?#{@agent-status-internal-title-busy},#{pane_id},}' |
        while IFS= read -r agent_pane; do
            [ -n "$agent_pane" ] || continue
            agent_tmux set-option -pu -t "$agent_pane" @agent-status-internal-title-busy 2>/dev/null || :
        done
fi

# Shared functions and socket selection stay in this process.
# shellcheck source=scripts/preset.sh
. "$agent_dir/scripts/preset.sh"
agent_apply_preset "$agent_mode"
