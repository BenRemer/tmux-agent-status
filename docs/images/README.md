# Demo images

The README images are rendered by `tools/render_demo.py`. It runs the plugin on
a temporary tmux server, with harmless stand-in `codex` and `claude` commands,
and draws the real status-line output. Captions and the terminal frame are
added by the renderer. `bell.png` is the Nerd Font bell, drawn the same way,
because GitHub can't display Nerd Font glyphs.

To regenerate:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements-images.txt
.venv/bin/python tools/render_demo.py \
  --font /path/to/DejaVuSansMono.ttf \
  --icon-font /path/to/FiraCodeNerdFontMono-Regular.ttf
```

Fonts are not bundled. Pass `--emoji-font` only when rendering with
`@agent-status-icons 'emoji'`. `TMUX_BIN` selects another tmux binary.
