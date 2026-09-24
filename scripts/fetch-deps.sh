#!/usr/bin/env bash
# Download the pinned JS/CSS dependencies of the Markdown preview and verify
# them against scripts/vendor.sha256. Safe to re-run: verified files are kept.
#
# Files come from cdn.jsdelivr.net; if that fails, from the npm registry
# tarball of the same package version (jsDelivr serves npm files unchanged,
# so both sources must match the same checksums).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$SCRIPT_DIR/../data/web"
SUMS="$SCRIPT_DIR/vendor.sha256"

KATEX="katex@0.16.11"

# destination (relative to WEB_DIR) | npm package@version | path inside the package
FILES=(
    "js/purify.min.js|dompurify@3.2.7|dist/purify.min.js"
    "js/markdown-it.min.js|markdown-it@14.1.0|dist/markdown-it.min.js"
    "js/markdown-it-footnote.min.js|markdown-it-footnote@3.0.3|dist/markdown-it-footnote.min.js"
    "js/katex.min.js|$KATEX|dist/katex.min.js"
    "js/auto-render.min.js|$KATEX|dist/contrib/auto-render.min.js"
    "js/highlight.min.js|@highlightjs/cdn-assets@11.9.0|highlight.min.js"
    "js/mermaid.min.js|mermaid@11.12.0|dist/mermaid.min.js"
    "css-vendor/katex.min.css|$KATEX|dist/katex.min.css"
    "css-vendor/highlight-light.min.css|@highlightjs/cdn-assets@11.9.0|styles/github.min.css"
    "css-vendor/highlight-dark.min.css|@highlightjs/cdn-assets@11.9.0|styles/github-dark.min.css"
    "css-vendor/github-markdown.css|github-markdown-css@5.9.0|github-markdown.css"
)
for font in AMS-Regular Caligraphic-Bold Caligraphic-Regular Fraktur-Bold Fraktur-Regular \
            Main-Bold Main-BoldItalic Main-Italic Main-Regular Math-BoldItalic Math-Italic \
            SansSerif-Bold SansSerif-Italic SansSerif-Regular Script-Regular \
            Size1-Regular Size2-Regular Size3-Regular Size4-Regular Typewriter-Regular; do
    FILES+=("css-vendor/fonts/KaTeX_$font.woff2|$KATEX|dist/fonts/KaTeX_$font.woff2")
done

if [[ ! -f "$SUMS" ]]; then
    echo "Missing checksum list: $SUMS" >&2
    exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

expected_sum() {
    awk -v f="$1" '$2 == f { print $1 }' "$SUMS"
}

is_valid() {
    local dest="$1" want
    want="$(expected_sum "$dest")"
    [[ -n "$want" && -f "$WEB_DIR/$dest" ]] &&
        [[ "$(sha256sum "$WEB_DIR/$dest" | cut -d' ' -f1)" == "$want" ]]
}

# Extract an npm tarball once and print the directory holding its files.
npm_package_dir() {
    local spec="$1" name version dir
    name="${spec%@*}"
    version="${spec##*@}"
    dir="$TMP_DIR/$(echo "$spec" | tr '/@' '__')"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        curl -fsSL "https://registry.npmjs.org/$name/-/${name##*/}-$version.tgz" |
            tar xz -C "$dir"
    fi
    echo "$dir/package"
}

fetch() {
    local dest="$1" spec="$2" path="$3" out="$WEB_DIR/$1"
    mkdir -p "$(dirname "$out")"
    if curl -fsSL --retry 2 "https://cdn.jsdelivr.net/npm/$spec/$path" -o "$out.part" 2>/dev/null; then
        mv "$out.part" "$out"
    else
        rm -f "$out.part"
        cp "$(npm_package_dir "$spec")/$path" "$out"
    fi
}

echo "Fetching preview dependencies into $WEB_DIR"
failed=0
for entry in "${FILES[@]}"; do
    IFS='|' read -r dest spec path <<<"$entry"
    if is_valid "$dest"; then
        continue
    fi
    echo "  -> $dest ($spec)"
    fetch "$dest" "$spec" "$path" || true
    if ! is_valid "$dest"; then
        echo "     checksum mismatch or download failed: $dest" >&2
        rm -f "$WEB_DIR/$dest"
        failed=1
    fi
done

if [[ $failed -ne 0 ]]; then
    echo "Some dependencies could not be verified." >&2
    exit 1
fi
echo "All ${#FILES[@]} files present and verified."
