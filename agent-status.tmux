#!/bin/sh
# TPM entry point. All shell work happens at load time.
set -eu

agent_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
agent_bin=${TMUX_BIN:-tmux}
agent_socket=
if [ "${1-}" = "--socket" ] && [ "$#" -eq 2 ]; then
    agent_socket=$2
elif [ "$#" -ne 0 ]; then
    printf '%s\n' 'Usage: agent-status.tmux [--socket PATH]' >&2
    exit 2
elif [ -n "${TMUX-}" ]; then
    # The final two comma-separated fields are the server PID and session ID.
    agent_socket=${TMUX%,*}
    agent_socket=${agent_socket%,*}
fi
if [ -z "$agent_socket" ]; then
    printf '%s\n' 'tmux-agent-status: load with tmux run-shell, or specify --socket PATH.' >&2
    exit 2
fi

agent_tmux() { "$agent_bin" -S "$agent_socket" "$@"; }
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

agent_mode=$(agent_input @agent-status-preset none)
case "$agent_mode" in
    none) agent_running_default=; agent_bell_default= ;;
    compact)
        agent_running_default='bg=#30464b,fg=#cad3f5'
        agent_bell_default='bg=#eed49f,fg=#181926,bold'
        ;;
    *) agent_warn '@agent-status-preset must be none or compact'; exit 1 ;;
esac

agent_running_icon=$(agent_input @agent-status-running-icon '⚙')
agent_bell_icon=$(agent_input @agent-status-bell-icon '🔔')
agent_command_pattern=$(agent_input @agent-status-command-pattern '^(codex|claude|agy)$')
agent_title_pattern=$(agent_input @agent-status-agent-title-pattern '^✳ ')
agent_busy_pattern=$(agent_input @agent-status-busy-title-pattern '^(⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏) ')
agent_running_style=$(agent_input @agent-status-running-style "$agent_running_default")
agent_bell_style=$(agent_input @agent-status-bell-style "$agent_bell_default")

# Inputs are passed as individual arguments, never evaluated as shell code.
for agent_value in "$agent_running_icon" "$agent_bell_icon" \
    "$agent_command_pattern" "$agent_title_pattern" "$agent_busy_pattern" \
    "$agent_running_style" "$agent_bell_style"; do
    case "$agent_value" in
        *'
'*) agent_warn 'icons, styles, and patterns must each be a single line'; exit 1 ;;
    esac
done
for agent_pattern in "$agent_command_pattern" "$agent_title_pattern" "$agent_busy_pattern"; do
    agent_regex_result=0
    printf '' | grep -E -e "$agent_pattern" >/dev/null 2>&1 || agent_regex_result=$?
    if [ "$agent_regex_result" -gt 1 ]; then
        agent_warn 'invalid recognition regular expression; no settings changed.'
        exit 1
    fi
done

# A literal bg/fg color from a style, for tinting themes with inline colors.
agent_style_color() {
    agent_color=$(printf '%s\n' "$1" | tr ', ' '\n\n' | sed -n "s/^$2=//p" | tail -n 1)
    case "$agent_color" in
        *[!#A-Za-z0-9]*) ;;
        *) printf '%s' "$agent_color" ;;
    esac
}

# Resolved defaults never overwrite user input options.
agent_tmux set-option -g @agent-status-internal-running-icon "$agent_running_icon"
agent_tmux set-option -g @agent-status-internal-bell-icon "$agent_bell_icon"
agent_tmux set-option -g @agent-status-internal-command-pattern "$agent_command_pattern"
agent_tmux set-option -g @agent-status-internal-title-pattern "$agent_title_pattern"
agent_tmux set-option -g @agent-status-internal-busy-pattern "$agent_busy_pattern"
agent_tmux set-option -g @agent-status-internal-running-style "$agent_running_style"
agent_tmux set-option -g @agent-status-internal-bell-style "$agent_bell_style"
agent_tmux set-option -g @agent-status-internal-running-bg "$(agent_style_color "$agent_running_style" bg)"
agent_tmux set-option -g @agent-status-internal-running-fg "$(agent_style_color "$agent_running_style" fg)"
agent_tmux set-option -g @agent-status-internal-bell-bg "$(agent_style_color "$agent_bell_style" bg)"
agent_tmux set-option -g @agent-status-internal-bell-fg "$(agent_style_color "$agent_bell_style" fg)"
agent_tmux source-file "$agent_dir/agent-status.conf"

# Shared functions and socket selection stay in this process.
# shellcheck source=scripts/preset.sh
. "$agent_dir/scripts/preset.sh"
agent_apply_preset "$agent_mode"
