"""Window formats from popular tmux themes, for compact-preset tests.

Each entry is (window-status-format, window-status-current-format, options).
Formats are copied from each theme's source with its default colors filled in
for shell variables. `options` are tmux options the format refers to.
"""

ARROW, THIN = "\ue0b0", "\ue0b1"  # Powerline arrows
ROUND_LEFT, ROUND_RIGHT = "\ue0b6", "\ue0b4"

# catppuccin/tmux v2 keeps references to its palette options in the format.
CATPPUCCIN_PALETTE = {
    "@thm_overlay_2": "#9399b2", "@thm_surface_0": "#313244",
    "@thm_surface_1": "#45475a", "@thm_mauve": "#cba6f7",
}

THEMES = {
    # tmux's own default.
    "tmux-default": (
        "#I:#W#{?window_flags,#{window_flags}, }",
        "#I:#W#{?window_flags,#{window_flags}, }",
        {},
    ),
    # catppuccin/tmux catppuccin_tmux.conf, default "basic" style.
    "catppuccin": (
        "#[fg=#11111b,bg=#{@thm_overlay_2}] #I #[fg=#cdd6f4,bg=#{@thm_surface_0}] #T ",
        "#[fg=#11111b,bg=#{@thm_mauve}] #I #[fg=#cdd6f4,bg=#{@thm_surface_1}] #T ",
        CATPPUCCIN_PALETTE,
    ),
    # catppuccin/tmux with @catppuccin_window_status_style 'rounded'.
    "catppuccin-rounded": (
        f"#[fg=#11111b,bg=#{{@thm_overlay_2}}]#[fg=#181825,reverse]{ROUND_LEFT}#[none]#I "
        f"#[fg=#cdd6f4,bg=#{{@thm_surface_0}}] #T#[fg=#181825,reverse]{ROUND_RIGHT}#[none]",
        f"#[fg=#11111b,bg=#{{@thm_mauve}}]#[fg=#181825,reverse]{ROUND_LEFT}#[none]#I "
        f"#[fg=#cdd6f4,bg=#{{@thm_surface_1}}] #T#[fg=#181825,reverse]{ROUND_RIGHT}#[none]",
        CATPPUCCIN_PALETTE,
    ),
    # dracula/tmux scripts/dracula.sh, default options.
    "dracula": (
        "#[fg=#f8f8f2]#[bg=#44475a] #I #W",
        f"#[fg=#44475a]#[bg=#6272a4]{ARROW}#[fg=#f8f8f2]#[bg=#6272a4] #I #W "
        f"#[fg=#6272a4]#[bg=#44475a]{ARROW}",
        {},
    ),
    # nordtheme/tmux src/nord-status-content.conf.
    "nord": (
        f"#[fg=black,bg=brightblack,nobold,noitalics,nounderscore]{ARROW} "
        f"#[fg=white,bg=brightblack]#I #[fg=white,bg=brightblack,nobold,noitalics,nounderscore]"
        f"{THIN} #[fg=white,bg=brightblack]#W #F "
        f"#[fg=brightblack,bg=black,nobold,noitalics,nounderscore]{ARROW}",
        f"#[fg=black,bg=cyan,nobold,noitalics,nounderscore]{ARROW} #[fg=black,bg=cyan]#I "
        f"#[fg=black,bg=cyan,nobold,noitalics,nounderscore]{THIN} #[fg=black,bg=cyan]#W #F "
        f"#[fg=cyan,bg=black,nobold,noitalics,nounderscore]{ARROW}",
        {},
    ),
    # egel/tmux-gruvbox src/theme_gruvbox_dark.sh.
    "gruvbox": (
        f"#[bg=#504945,fg=#3c3836,noitalics]{ARROW}#[bg=#504945,fg=#ebdbb2] #I {THIN}"
        "#[bg=#504945,fg=#ebdbb2] #W #{?window_end_flag,#[bg=#3c3836],#[bg=#3c3836]}"
        f"#[fg=#504945,noitalics]{ARROW}",
        f"#[bg=#fabd2f,fg=#3c3836,nobold,noitalics,nounderscore]{ARROW}"
        f"#[bg=#fabd2f,fg=#504945] #I {THIN}#[bg=#fabd2f,fg=#504945,bold] "
        "#W#{?window_zoomed_flag,*Z,} #{?window_end_flag,#[bg=#3c3836],#[bg=#3c3836]}"
        f"#[fg=#fabd2f,nobold,noitalics,nounderscore]{ARROW}",
        {},
    ),
    # odedlaz/tmux-onedark-theme.
    "onedark": (
        f"#[fg=#282c34,bg=#282c34,nobold,nounderscore,noitalics]{ARROW}"
        f"#[fg=#aab2bf,bg=#282c34] #I {THIN} #W "
        f"#[fg=#282c34,bg=#282c34,nobold,nounderscore,noitalics]{ARROW}",
        f"#[fg=#282c34,bg=#3e4452,nobold,nounderscore,noitalics]{ARROW}"
        f"#[fg=#aab2bf,bg=#3e4452,nobold] #I {THIN} #W "
        f"#[fg=#3e4452,bg=#282c34,nobold,nounderscore,noitalics]{ARROW}",
        {},
    ),
    # wfxr/tmux-power, default gold theme.
    "tmux-power": (
        f"#[fg=#262626,bg=#3a3a3a]{ARROW}#[fg=#ffb86c,bg=#3a3a3a] #I:#W#F "
        f"#[fg=#3a3a3a,bg=#262626]{ARROW}",
        f"#[fg=#262626,bg=#ffb86c]{ARROW}#[fg=#262626,bg=#ffb86c,bold] #I:#W#F "
        f"#[fg=#ffb86c,bg=#262626,none]{ARROW}",
        {},
    ),
    # jimeh/tmux-themepack powerline/default: plain text, colors from
    # window-status-style.
    "themepack": (
        "  #I:#W#F  ",
        f"#[fg=colour235,bg=colour233]{ARROW}#[fg=colour45,nobold] #I:#W#F "
        f"#[fg=colour235,bg=colour233,nobold]{ARROW}",
        {},
    ),
}
