# Marker

A Markdown and plain-text editor for the Linux desktop, built with GTK 4,
libadwaita, GtkSourceView and WebKitGTK.

- Live preview with syntax highlighting, KaTeX math, Mermaid diagrams and footnotes
- Tabs, file explorer, recent files, minimap
- Find & replace, regex search, search across a folder
- Keeps each file's encoding and line endings; saves atomically
- Formatting toolbar and shortcuts (Ctrl+B, Ctrl+I, Ctrl+L, headings, lists)

## Requirements

| Component | Minimum |
|---|---|
| Python | 3.10 |
| GTK | 4.6 |
| libadwaita | 1.1 |
| GtkSourceView | 5 |
| WebKitGTK | 6.0 API (2.40+) |

These come from your distribution, not from PyPI. Distributions that ship
all of them include Ubuntu 24.04, Debian 13 and Fedora 39 or newer.
Development and CI use Ubuntu 24.04 (GTK 4.14, libadwaita 1.5).

On Debian/Ubuntu/Mint:

```sh
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
                 gir1.2-gtksource-5 gir1.2-webkit-6.0
```

On Fedora:

```sh
sudo dnf install python3-gobject gtk4 libadwaita gtksourceview5 webkitgtk6.0
```

## Install

```sh
bash setup.sh
```

The script checks the GTK stack, downloads the preview's JavaScript/CSS
libraries (pinned versions, verified against `scripts/vendor.sha256`), and
installs a launcher (`~/.local/bin/marker`), an icon and a desktop entry for
your user. It never modifies files in the repository and is safe to re-run.

Then run `marker`, `marker notes.md`, or open Marker from the app menu.

### Other ways to run it

```sh
bash scripts/fetch-deps.sh    # once: download the preview libraries
python3 -m marker             # from the repository root
bin/marker file.md            # from anywhere, keeps relative paths
```

To install it as a Python package (e.g. into a venv created with
`--system-site-packages`, so it can see PyGObject):

```sh
bash scripts/fetch-deps.sh
pip install .
```

## Configuration

Preferences (Ctrl+,) are saved to `~/.config/marker/settings.json` and apply
immediately to every tab. Recent files are kept in
`~/.config/marker/recents.json`.

## Security

Markdown files can contain raw HTML. The preview sanitizes it with DOMPurify,
runs Mermaid in strict mode, and uses a Content Security Policy that blocks
network requests from scripts. The page cannot read other local files.
Links open in your browser (http, https and mailto only), and links to local
text files open in a Marker tab.

## Development

```sh
sudo apt install python3-pytest xvfb    # plus the packages above
bash scripts/fetch-deps.sh               # the preview tests need the libraries
xvfb-run -a python3 -m pytest            # GUI tests need a display
ruff check .
```

`scripts/package.sh` creates `dist/marker-<version>.zip` from the committed
sources.

To update a preview library, change its version in `scripts/fetch-deps.sh`,
then update the matching lines in `scripts/vendor.sha256` with the SHA-256 of
the new files.

## License

GPL-3.0-or-later
