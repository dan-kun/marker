#!/usr/bin/env bash
# Creates a distributable zip of Marker (excludes git, pycache, vendor assets)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION=$(python3 -c "from marker import __version__; print(__version__)" 2>/dev/null || echo "0.1.0")
OUTPUT="$PROJECT_DIR/../marker-$VERSION.zip"

cd "$PROJECT_DIR/.."

zip -r "$OUTPUT" marker/ \
    --exclude "marker/.git/*" \
    --exclude "marker/__pycache__/*" \
    --exclude "marker/marker/__pycache__/*" \
    --exclude "marker/data/web/js/*" \
    --exclude "marker/data/web/css-vendor/*" \
    --exclude "*.pyc" \
    --exclude "*.egg-info/*"

echo "Created: $OUTPUT"
echo "Size: $(du -sh "$OUTPUT" | cut -f1)"
echo ""
echo "The recipient runs:"
echo "  unzip marker-$VERSION.zip"
echo "  cd marker"
echo "  bash setup.sh"
