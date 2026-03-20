#!/usr/bin/env bash
# Marker - Setup script
# Installs system dependencies, downloads JS/CSS assets, and registers the app.
# Compatible with: Ubuntu 20.04+, Linux Mint 20+, Debian 11+

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}→${NC} $*"; }
ok()      { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
die()     { echo -e "${RED}✗ Error:${NC} $*"; exit 1; }

echo ""
echo "  ╔══════════════════════════════╗"
echo "  ║   Marker - Setup             ║"
echo "  ║   Markdown & TXT Editor      ║"
echo "  ╚══════════════════════════════╝"
echo ""

# ── 1. Check Python ────────────────────────────────────────────────────────
info "Checking Python 3.10+..."
if ! command -v python3 &>/dev/null; then
    die "Python 3 not found. Install it with: sudo apt install python3"
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 || ("$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10) ]]; then
    die "Python 3.10+ required (found $PYTHON_VERSION). Upgrade Python or use a newer OS release."
fi
ok "Python $PYTHON_VERSION found"

# ── 2. Install system packages ────────────────────────────────────────────
info "Installing system packages (requires sudo)..."

PACKAGES=(
    python3-gi
    python3-gi-cairo
    gir1.2-gtk-4.0
    gir1.2-adwaita-1
    gir1.2-gtksource-5
    gir1.2-webkit-6.0
)

MISSING=()
for pkg in "${PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null 2>&1; then
        MISSING+=("$pkg")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "  Packages to install: ${MISSING[*]}"
    sudo apt-get update -qq
    sudo apt-get install -y "${MISSING[@]}"
    ok "Packages installed"
else
    ok "All system packages already installed"
fi

# ── 3. Verify GTK4 works ──────────────────────────────────────────────────
info "Verifying GTK4 + GtkSource + WebKit..."
python3 - <<'PYCHECK'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")
gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, Adw, GtkSource, WebKit
print("  All Python bindings OK")
PYCHECK
ok "GTK4 bindings verified"

# ── 4. Download JS/CSS vendor assets ──────────────────────────────────────
JS_DIR="$SCRIPT_DIR/data/web/js"
if [[ ! -f "$JS_DIR/markdown-it.min.js" ]]; then
    info "Downloading JS/CSS vendor assets..."
    bash "$SCRIPT_DIR/scripts/fetch-deps.sh"
    ok "Vendor assets downloaded"
else
    ok "Vendor assets already present"
fi

# ── 5. Install desktop entry + icon ───────────────────────────────────────
info "Installing desktop integration..."

# Update Exec path to point to this installation
DESKTOP_FILE="$SCRIPT_DIR/data/marker.desktop"
LAUNCHER="$SCRIPT_DIR/bin/marker"

# Rewrite launcher with correct path
cat > "$LAUNCHER" <<LAUNCHER
#!/usr/bin/env bash
cd "$SCRIPT_DIR"
exec python3 -m marker "\$@"
LAUNCHER
chmod +x "$LAUNCHER"

# Rewrite .desktop Exec with correct path
sed -i "s|Exec=.*|Exec=$LAUNCHER %F|" "$DESKTOP_FILE"

bash "$SCRIPT_DIR/scripts/install-desktop.sh"
ok "Desktop integration installed"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "  Run Marker with:"
echo "    python3 -m marker              # from this directory"
echo "    python3 -m marker file.md      # open a file directly"
echo "    $LAUNCHER"
echo ""
echo "  Or find 'Marker' in your application menu."
echo ""
