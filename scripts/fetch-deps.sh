#!/usr/bin/env bash
# Download JS/CSS vendor dependencies for Marker preview
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JS_DIR="$SCRIPT_DIR/../data/web/js"
CSS_DIR="$SCRIPT_DIR/../data/web/css-vendor"

mkdir -p "$JS_DIR" "$CSS_DIR"

echo "Downloading vendor dependencies..."

# markdown-it (latest stable)
echo "  -> markdown-it..."
curl -fsSL "https://cdn.jsdelivr.net/npm/markdown-it@14/dist/markdown-it.min.js" \
    -o "$JS_DIR/markdown-it.min.js"

# markdown-it-footnote
echo "  -> markdown-it-footnote..."
curl -fsSL "https://cdn.jsdelivr.net/npm/markdown-it-footnote@3/dist/markdown-it-footnote.min.js" \
    -o "$JS_DIR/markdown-it-footnote.min.js"

# KaTeX
KATEX_VERSION="0.16.11"
echo "  -> KaTeX $KATEX_VERSION..."
curl -fsSL "https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/katex.min.js" \
    -o "$JS_DIR/katex.min.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/contrib/auto-render.min.js" \
    -o "$JS_DIR/auto-render.min.js"
curl -fsSL "https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/katex.min.css" \
    -o "$CSS_DIR/katex.min.css"

# KaTeX fonts
echo "  -> KaTeX fonts..."
mkdir -p "$CSS_DIR/fonts"
FONTS=(
    "KaTeX_AMS-Regular.woff2"
    "KaTeX_Caligraphic-Bold.woff2"
    "KaTeX_Caligraphic-Regular.woff2"
    "KaTeX_Fraktur-Bold.woff2"
    "KaTeX_Fraktur-Regular.woff2"
    "KaTeX_Main-Bold.woff2"
    "KaTeX_Main-BoldItalic.woff2"
    "KaTeX_Main-Italic.woff2"
    "KaTeX_Main-Regular.woff2"
    "KaTeX_Math-BoldItalic.woff2"
    "KaTeX_Math-Italic.woff2"
    "KaTeX_SansSerif-Bold.woff2"
    "KaTeX_SansSerif-Italic.woff2"
    "KaTeX_SansSerif-Regular.woff2"
    "KaTeX_Script-Regular.woff2"
    "KaTeX_Size1-Regular.woff2"
    "KaTeX_Size2-Regular.woff2"
    "KaTeX_Size3-Regular.woff2"
    "KaTeX_Size4-Regular.woff2"
    "KaTeX_Typewriter-Regular.woff2"
)
for font in "${FONTS[@]}"; do
    curl -fsSL "https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/fonts/$font" \
        -o "$CSS_DIR/fonts/$font" 2>/dev/null || true
done

# highlight.js
echo "  -> highlight.js..."
curl -fsSL "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js" \
    -o "$JS_DIR/highlight.min.js"
curl -fsSL "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css" \
    -o "$CSS_DIR/highlight-light.min.css"
curl -fsSL "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css" \
    -o "$CSS_DIR/highlight-dark.min.css"

# Mermaid
echo "  -> Mermaid..."
curl -fsSL "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js" \
    -o "$JS_DIR/mermaid.min.js"

# GitHub Markdown CSS
echo "  -> GitHub Markdown CSS..."
curl -fsSL "https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown.css" \
    -o "$CSS_DIR/github-markdown.css"

echo ""
echo "Done! Vendor dependencies downloaded to:"
echo "  JS:  $JS_DIR"
echo "  CSS: $CSS_DIR"
