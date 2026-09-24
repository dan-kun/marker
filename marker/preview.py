"""WebKit-based Markdown preview."""

import base64
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")

from gi.repository import Adw, Gdk, Gio, GObject, Gtk, WebKit

from .filetypes import is_shown

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "web")

# Links with these schemes open in the user's default app; anything else
# (javascript:, file: pointing at non-text files, custom handlers) is ignored.
_EXTERNAL_SCHEMES = ("http", "https", "mailto")

_FALLBACK_HTML = """<!DOCTYPE html>
<html><body style="font-family:sans-serif;padding:2rem;color:#666">
<h3>Vendor assets not found</h3>
<p>Run <code>bash scripts/fetch-deps.sh</code> to download JS/CSS dependencies.</p>
<script>
function render(text) {
  document.body.innerHTML = '<pre style="white-space:pre-wrap">' +
    text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>';
}
function setTheme(isDark) {}
function setScrollPercent(pct) {}
</script>
</body></html>"""


def _preview_uri() -> str:
    path = os.path.join(WEB_DIR, "preview.html")
    if os.path.exists(os.path.join(WEB_DIR, "js", "markdown-it.min.js")):
        return Gio.File.new_for_path(path).get_uri()
    encoded = base64.b64encode(_FALLBACK_HTML.encode()).decode()
    return f"data:text/html;base64,{encoded}"


class MarkdownPreview(Gtk.Box):
    """WebKit preview panel for rendered Markdown."""

    __gsignals__ = {
        # A link to a local text file was clicked
        "open-file": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._zoom_level = 1.0
        self._ready = False
        self._disposed = False
        self._text: str | None = None
        self._base_uri: str | None = None
        self._page_uri = _preview_uri()

        style_manager = Adw.StyleManager.get_default()
        self._is_dark = style_manager.get_dark()
        # StyleManager is a process-wide singleton: this handler must be
        # disconnected in dispose() or it keeps the whole tab alive.
        self._style_handler = style_manager.connect("notify::dark", self._on_theme_changed)

        self._setup_webview()

    def _setup_webview(self):
        self._webview = WebKit.WebView()
        self._webview.set_vexpand(True)
        self._webview.set_hexpand(True)

        # Documents may come from anywhere: their HTML is sanitized in
        # preview.html, and the page may not read other local files.
        settings = self._webview.get_settings()
        settings.set_enable_javascript(True)
        settings.set_allow_file_access_from_file_urls(False)
        settings.set_allow_universal_access_from_file_urls(False)
        settings.set_javascript_can_open_windows_automatically(False)
        settings.set_enable_developer_extras(False)

        self._webview_handlers = [
            self._webview.connect("load-changed", self._on_load_changed),
            self._webview.connect("decide-policy", self._on_decide_policy),
            self._webview.connect("web-process-terminated", self._on_web_process_terminated),
        ]
        self.append(self._webview)
        self._webview.load_uri(self._page_uri)

    def dispose(self):
        """Disconnect global signals and stop the web process."""
        if self._disposed:
            return
        self._disposed = True
        Adw.StyleManager.get_default().disconnect(self._style_handler)
        # These closures reference self; left connected they form a cycle
        # through the WebView that Python's GC cannot break.
        for handler in self._webview_handlers:
            self._webview.disconnect(handler)
        self._webview_handlers = []
        self._webview.terminate_web_process()

    # ── WebView events ─────────────────────────────────────────────────────

    def _on_load_changed(self, webview, event):
        if event == WebKit.LoadEvent.STARTED:
            self._ready = False
        elif event == WebKit.LoadEvent.FINISHED:
            self._ready = True
            self._js_set_theme()
            if self._text is not None:
                self._js_render()

    def _on_web_process_terminated(self, webview, reason):
        if not self._disposed:
            self._ready = False
            webview.load_uri(self._page_uri)

    def _on_decide_policy(self, webview, decision, kind):
        if kind not in (WebKit.PolicyDecisionType.NAVIGATION_ACTION,
                        WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
            return False
        action = decision.get_navigation_action()
        uri = action.get_request().get_uri()
        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION and \
                uri.split("#", 1)[0] == self._page_uri.split("#", 1)[0]:
            return False  # the preview page itself, or an in-page #anchor

        decision.ignore()
        if action.is_user_gesture():
            self._open_link(uri)
        return True

    def _open_link(self, uri: str):
        scheme = uri.split(":", 1)[0].lower()
        if scheme == "file":
            path = Gio.File.new_for_uri(uri).get_path()
            if path and os.path.isfile(path) and is_shown(path):
                self.emit("open-file", path)
            return
        if scheme not in _EXTERNAL_SCHEMES:
            return
        window = self.get_root()
        if hasattr(Gtk, "UriLauncher"):  # GTK ≥ 4.10
            Gtk.UriLauncher.new(uri).launch(window, None, None, None)
        else:
            Gtk.show_uri(window, uri, Gdk.CURRENT_TIME)

    def _on_theme_changed(self, style_manager, param):
        self._is_dark = style_manager.get_dark()
        self._js_set_theme()

    # ── JS Bridge ──────────────────────────────────────────────────────────

    def _js(self, script: str):
        if self._ready and not self._disposed:
            self._webview.evaluate_javascript(script, -1, None, None, None, None, None)

    def _js_render(self):
        self._js(f"render({json.dumps(self._text)}, {json.dumps(self._base_uri)})")

    def _js_set_theme(self):
        self._js(f"setTheme({json.dumps(self._is_dark)})")

    # ── Public API ─────────────────────────────────────────────────────────

    def render(self, text: str):
        self._text = text
        self._js_render()  # no-op until the page has loaded; flushed on FINISHED

    def set_base_dir(self, directory: str | None):
        """Resolve relative links and images against the document's folder."""
        uri = Gio.File.new_for_path(directory).get_uri().rstrip("/") + "/" if directory else None
        if uri != self._base_uri:
            self._base_uri = uri
            if self._text is not None:
                self._js_render()

    def scroll_to_fraction(self, fraction: float):
        self._js(f"setScrollPercent({fraction:.4f})")

    def get_webview(self) -> WebKit.WebView:
        return self._webview

    def zoom_in(self):
        self._zoom_level = min(3.0, self._zoom_level + 0.1)
        self._webview.set_zoom_level(self._zoom_level)

    def zoom_out(self):
        self._zoom_level = max(0.3, self._zoom_level - 0.1)
        self._webview.set_zoom_level(self._zoom_level)

    def zoom_reset(self):
        self._zoom_level = 1.0
        self._webview.set_zoom_level(self._zoom_level)
