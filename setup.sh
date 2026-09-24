#!/usr/bin/env bash
# Marker - Setup script
# Installs system dependencies, downloads the preview's JS/CSS assets, and
# registers the app for the current user.
#
# Package installation uses apt (Debian, Ubuntu, Linux Mint and derivatives).
# On other distributions install the equivalent packages yourself; the rest
# of the script works everywhere. Requirements: Python 3.10+, GTK 4.6+,
# libadwaita 1.1+, GtkSourceView 5 and WebKitGTK 6.0 (e.g. Ubuntu 24.04,
# Debian 13, Fedora 39 or newer).

set -euo pipefail

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
command -v python3 &>/dev/null || die "Python 3 not found. Install it with your package manager."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' ||
    die "Python 3.10+ required (found $(python3 -V 2>&1))."
ok "$(python3 -V) found"

# ── 2. Install system packages ────────────────────────────────────────────
PACKAGES=(
    python3-gi
    python3-gi-cairo
    gir1.2-gtk-4.0
    gir1.2-adw-1
    gir1.2-gtksource-5
    gir1.2-webkit-6.0
)

if command -v dpkg &>/dev/null && command -v apt-get &>/dev/null; then
    info "Checking system packages..."
    MISSING=()
    for pkg in "${PACKAGES[@]}"; do
        dpkg -s "$pkg" &>/dev/null || MISSING+=("$pkg")
    done
    if [[ ${#MISSING[@]} -gt 0 ]]; then
        echo "  Packages to install (requires sudo): ${MISSING[*]}"
        sudo apt-get update -qq
        sudo apt-get install -y "${MISSING[@]}" ||
            die "Could not install ${MISSING[*]}. Your release may be too old for WebKitGTK 6.0."
        ok "Packages installed"
    else
        ok "All system packages already installed"
    fi
else
    warn "Not a Debian-based system: install GTK 4, libadwaita, GtkSourceView 5,"
    warn "WebKitGTK 6.0 and PyGObject with your package manager."
fi

# ── 3. Verify the GTK stack and minimum versions ──────────────────────────
info "Verifying GTK4 + libadwaita + GtkSourceView + WebKit..."
python3 - <<'PYCHECK' || die "The GTK stack is missing or too old (see above)."
import sys
import gi
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("GtkSource", "5")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Adw, Gtk, GtkSource, WebKit  # noqa: F401
except (ValueError, ImportError) as e:
    print(f"  {e}")
    sys.exit(1)
gtk = (Gtk.get_major_version(), Gtk.get_minor_version())
adw = (Adw.get_major_version(), Adw.get_minor_version())
print(f"  GTK {gtk[0]}.{gtk[1]}, libadwaita {adw[0]}.{adw[1]}, "
      f"WebKitGTK {WebKit.get_major_version()}.{WebKit.get_minor_version()}")
if gtk < (4, 6) or adw < (1, 1):
    print("  Marker needs GTK 4.6+ and libadwaita 1.1+")
    sys.exit(1)
PYCHECK
ok "GTK4 bindings verified"

# ── 4. Download and verify JS/CSS vendor assets ───────────────────────────
info "Checking preview assets..."
bash "$SCRIPT_DIR/scripts/fetch-deps.sh"
ok "Vendor assets verified"

# ── 5. Install launcher, icon and desktop entry ───────────────────────────
info "Installing desktop integration..."
bash "$SCRIPT_DIR/scripts/install-desktop.sh"
ok "Desktop integration installed"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "  Run Marker with:"
echo "    marker                  # from any directory (~/.local/bin/marker)"
echo "    marker notes.md         # open files directly"
echo "    $SCRIPT_DIR/bin/marker"
echo ""
echo "  Or find 'Marker' in your application menu."
echo ""
