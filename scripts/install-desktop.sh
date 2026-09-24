#!/usr/bin/env bash
# Install Marker's launcher, icon and desktop entry for the current user
# (~/.local, no sudo). Files in this repository are not modified.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_ID="io.github.dan_kun.Marker"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
ICON_DIR="$DATA_HOME/icons/hicolor"
APPS_DIR="$DATA_HOME/applications"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$PROJECT_DIR/bin/marker"

echo "Installing Marker desktop integration..."

# ── Remove files from older installs (app ID was "marker") ─────────────────
rm -f "$APPS_DIR/marker.desktop"
find "$ICON_DIR" -path '*/apps/marker.png' -delete 2>/dev/null || true
rm -f "$ICON_DIR/scalable/apps/marker.svg"

# ── Icons ──────────────────────────────────────────────────────────────────
SVG="$PROJECT_DIR/data/$APP_ID.svg"
for size in 16 22 24 32 48 64 128 256; do
    dir="$ICON_DIR/${size}x${size}/apps"
    mkdir -p "$dir"
    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert -w "$size" -h "$size" "$SVG" -o "$dir/$APP_ID.png"
    elif command -v inkscape &>/dev/null; then
        inkscape --export-type=png --export-width="$size" --export-height="$size" \
            --export-filename="$dir/$APP_ID.png" "$SVG" &>/dev/null
    elif command -v convert &>/dev/null; then
        convert -background none -resize "${size}x${size}" "$SVG" "$dir/$APP_ID.png"
    fi
done
mkdir -p "$ICON_DIR/scalable/apps"
cp "$SVG" "$ICON_DIR/scalable/apps/$APP_ID.svg"
echo "  -> icons"

# ── Launcher on PATH ───────────────────────────────────────────────────────
chmod +x "$LAUNCHER"
mkdir -p "$BIN_DIR"
ln -sf "$LAUNCHER" "$BIN_DIR/marker"
echo "  -> $BIN_DIR/marker"

# ── Desktop file (named after the app ID so Wayland shells match windows) ─
mkdir -p "$APPS_DIR"
sed "s|@LAUNCHER@|$LAUNCHER|" "$PROJECT_DIR/data/$APP_ID.desktop" > "$APPS_DIR/$APP_ID.desktop"
echo "  -> $APPS_DIR/$APP_ID.desktop"

# ── Caches ─────────────────────────────────────────────────────────────────
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$ICON_DIR" &>/dev/null || true
fi
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$APPS_DIR" &>/dev/null || true
fi

echo ""
echo "Done! Marker should now appear in your application menu."
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Note: add $BIN_DIR to your PATH to run 'marker' from a terminal." ;;
esac
