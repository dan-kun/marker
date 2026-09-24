#!/usr/bin/env bash
# Create a distributable zip of the committed sources (no vendor assets,
# caches or local changes). The recipient runs setup.sh, which downloads
# and verifies the vendor assets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

VERSION=$(python3 -c "import re; print(re.search(r'__version__ = \"(.+)\"', open('marker/__init__.py').read())[1])")
OUTPUT="$PROJECT_DIR/dist/marker-$VERSION.zip"
mkdir -p "$PROJECT_DIR/dist"

if ! git diff --quiet HEAD 2>/dev/null; then
    echo "Note: uncommitted changes are not included in the package." >&2
fi
git archive --format=zip --prefix="marker-$VERSION/" -o "$OUTPUT" HEAD

echo "Created: $OUTPUT"
echo "Size: $(du -sh "$OUTPUT" | cut -f1)"
echo ""
echo "The recipient runs:"
echo "  unzip marker-$VERSION.zip"
echo "  cd marker-$VERSION"
echo "  bash setup.sh"
