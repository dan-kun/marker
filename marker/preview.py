"""WebKit-based Markdown preview."""

import os
import json
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")

from gi.repository import Gtk, Adw, WebKit, GLib, GObject

# Path to the web assets directory
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "web")


class MarkdownPreview(Gtk.Box):
    """WebKit preview panel for rendered Markdown."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._zoom_level = 1.0
        self._ready = False
        self._pending_render: str | None = None
        self._pending_theme: bool | None = None

        self._setup_webview()
        self._setup_theme_sync()

    def _setup_webview(self):
        self._webview = WebKit.WebView()
        self._webview.set_vexpand(True)
        self._webview.set_hexpand(True)

        # Security: restrict to local files
        settings = self._webview.get_settings()
        settings.set_enable_javascript(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(False)
        settings.set_enable_developer_extras(False)

        self._webview.connect("load-changed", self._on_load_changed)
        self.append(self._webview)

        # Load the preview HTML
        preview_path = os.path.join(_DATA_DIR, "preview.html")
        if os.path.exists(preview_path):
            uri = f"file://{preview_path}"
        else:
            # Fallback minimal page if vendor assets not yet fetched
            uri = self._get_fallback_uri()
        self._webview.load_uri(uri)

    def _get_fallback_uri(self) -> str:
        html = """<!DOCTYPE html>
<html><body style="font-family:sans-serif;padding:2rem;color:#666">
<h3>Vendor assets not found</h3>
<p>Run <code>bash scripts/fetch-deps.sh</code> to download JS/CSS dependencies.</p>
<script>
function render(text) {
  document.body.innerHTML = '<pre style="white-space:pre-wrap">' +
    text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>';
}
function setTheme(isDark) {}
</script>
</body></html>"""
        import base64
        encoded = base64.b64encode(html.encode()).decode()
        return f"data:text/html;base64,{encoded}"

    def _setup_theme_sync(self):
        style_manager = Adw.StyleManager.get_default()
        style_manager.connect("notify::dark", self._on_theme_changed)
        # Initial theme
        self._is_dark = style_manager.get_dark()

    def _on_load_changed(self, webview, event):
        if event == WebKit.LoadEvent.FINISHED:
            self._ready = True
            # Apply initial theme
            self._js_set_theme(self._is_dark)
            # Flush pending render
            if self._pending_render is not None:
                self._js_render(self._pending_render)
                self._pending_render = None

    def _on_theme_changed(self, style_manager, param):
        self._is_dark = style_manager.get_dark()
        self._js_set_theme(self._is_dark)

    # ── JS Bridge ──────────────────────────────────────────────────────────

    def _js(self, script: str):
        self._webview.evaluate_javascript(script, -1, None, None, None, None, None)

    def _js_render(self, text: str):
        escaped = json.dumps(text)
        self._js(f"render({escaped})")

    def _js_set_theme(self, is_dark: bool):
        self._js(f"setTheme({str(is_dark).lower()})")

    # ── Public API ─────────────────────────────────────────────────────────

    def render(self, text: str):
        if self._ready:
            self._js_render(text)
        else:
            self._pending_render = text

    def zoom_in(self):
        self._zoom_level = min(3.0, self._zoom_level + 0.1)
        self._webview.set_zoom_level(self._zoom_level)

    def zoom_out(self):
        self._zoom_level = max(0.3, self._zoom_level - 0.1)
        self._webview.set_zoom_level(self._zoom_level)

    def zoom_reset(self):
        self._zoom_level = 1.0
        self._webview.set_zoom_level(self._zoom_level)
