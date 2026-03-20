#!/usr/bin/env bash
# Install Marker as a system app (no sudo needed — installs to ~/.local)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

ICON_DIR="$HOME/.local/share/icons/hicolor"
APPS_DIR="$HOME/.local/share/applications"

echo "Installing Marker desktop integration..."

# ── Icons ──────────────────────────────────────────────────────────────────
for size in 16 22 24 32 48 64 128 256; do
    dir="$ICON_DIR/${size}x${size}/apps"
    mkdir -p "$dir"

    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert -w $size -h $size "$PROJECT_DIR/data/marker.svg" \
            -o "$dir/marker.png" 2>/dev/null && echo "  -> icon ${size}x${size} (rsvg)"
    elif command -v inkscape &>/dev/null; then
        inkscape --export-type=png --export-width=$size --export-height=$size \
            --export-filename="$dir/marker.png" "$PROJECT_DIR/data/marker.svg" \
            &>/dev/null && echo "  -> icon ${size}x${size} (inkscape)"
    elif command -v convert &>/dev/null; then
        convert -background none -resize ${size}x${size} \
            "$PROJECT_DIR/data/marker.svg" "$dir/marker.png" \
            2>/dev/null && echo "  -> icon ${size}x${size} (imagemagick)"
    fi
done

# Also install scalable SVG
mkdir -p "$ICON_DIR/scalable/apps"
cp "$PROJECT_DIR/data/marker.svg" "$ICON_DIR/scalable/apps/marker.svg"
echo "  -> icon scalable (svg)"

# ── Desktop file ───────────────────────────────────────────────────────────
mkdir -p "$APPS_DIR"
cp "$PROJECT_DIR/data/marker.desktop" "$APPS_DIR/marker.desktop"
echo "  -> desktop file"

# ── Update icon cache ──────────────────────────────────────────────────────
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$ICON_DIR" 2>/dev/null && echo "  -> icon cache updated"
fi

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$APPS_DIR" 2>/dev/null && echo "  -> desktop database updated"
fi

echo ""
echo "Done! Marker should now appear in your application menu."
echo "If it doesn't show immediately, log out and back in, or run:"
echo "  xdg-desktop-menu forceupdate"
