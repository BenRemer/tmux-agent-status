# Demo image provenance

These images render **actual output from an isolated tmux server**.
`bell.png` is the default Nerd Font bell drawn by the same script, because
GitHub's fonts cannot display Nerd Font glyphs in the documentation. The demo
uses harmless executables named `codex` and `claude`, explicit activity titles
and events, and real terminal bells. It does not invoke a model, read a user's
configuration, or reproduce private terminal contents.

The terminal frame, captions, and legends are added by the renderer. The
demo's base theme makes the plugin's behavior easy to compare; installing the
plugin does not replace your theme with this one. The default bell is a Nerd
Font glyph; its appearance depends on the terminal font.

To regenerate:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements-images.txt
.venv/bin/python tools/render_demo.py \
  --font /path/to/DejaVuSansMono.ttf \
  --icon-font /path/to/FiraCodeNerdFontMono-Regular.ttf
```

Use a tmux version supported by the plugin. `TMUX_BIN` can select another
installed binary. The script requires a local PTY and permission to start a
temporary tmux server; it does not attach to your existing server.

The generated PNGs are committed so GitHub needs no external image host or
renderer. Fonts are not bundled. DejaVu Sans Mono and a Nerd Font, such as
FiraCode Nerd Font Mono, reproduce the images. Pass `--emoji-font` only when
rendering with `@agent-status-icons 'emoji'`. Fonts are supplied explicitly
rather than downloaded at runtime.
