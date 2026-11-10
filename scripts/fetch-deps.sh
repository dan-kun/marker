#!/usr/bin/env bash
# Download the pinned JS/CSS dependencies of the Markdown preview and verify
# them against scripts/vendor.sha256. Safe to re-run: verified files are kept.
#
# Files come from cdn.jsdelivr.net; if that fails, from the npm registry
# tarball of the same package version (jsDelivr serves npm files unchanged,
# so both sources must match the same checksums).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$SCRIPT_DIR/../marker/data/web"
SUMS="$SCRIPT_DIR/vendor.sha256"

LIST="$SCRIPT_DIR/vendor-files.txt"

# destination (relative to WEB_DIR) | npm package@version | path inside the package
mapfile -t FILES < <(grep -Ev '^[[:space:]]*(#|$)' "$LIST")

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
