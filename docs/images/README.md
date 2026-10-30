# Demo image provenance

These images render **actual output from an isolated tmux server**. The demo
uses harmless executables named `codex` and `claude`, explicit activity titles
and events, and real terminal bells. It does not invoke a model, read a user's
configuration, or reproduce private terminal contents.

The terminal frame, captions, and legends are added by the renderer. The
demo's base theme makes the plugin's behavior easy to compare; installing the
plugin does not replace your theme with this one. Emoji appearance depends
on the terminal and font.

To regenerate:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements-images.txt
.venv/bin/python tools/render_demo.py \
  --font /path/to/DejaVuSansMono.ttf \
  --emoji-font /path/to/NotoEmoji-Regular.ttf
```

Use a tmux version supported by the plugin. `TMUX_BIN` can select another
installed binary. The script requires a local PTY and permission to start a
temporary tmux server; it does not attach to your existing server.

The generated PNGs are committed so GitHub needs no external image host or
renderer. Fonts are not bundled. DejaVu fonts and Google Fonts' Noto Emoji
can be used to reproduce the images; the terminal font is supplied explicitly
rather than downloaded at runtime.
