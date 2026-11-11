"""Marker GTK4 Application."""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk

from . import __app_id__, __version__
from .window import MarkerWindow

# Adwaita's .dim-label is too faint for small text on a light background
# (about 3:1). This keeps secondary text above the 4.5:1 that WCAG asks for.
_CSS = """
.marker-dim { opacity: 0.72; }
"""


class MarkerApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.connect("activate", self._on_activate)
        self.connect("open", self._on_open)
        self._setup_actions()

    def _setup_actions(self):
        # Closing each window runs its unsaved-changes check; the app exits
        # when the last window is gone.
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit)
        self.add_action(quit_action)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def do_startup(self):
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(__app_id__)
        display = Gdk.Display.get_default()
        if display is None:
            return
        provider = Gtk.CssProvider()
        if hasattr(provider, "load_from_string"):  # GTK ≥ 4.12
            provider.load_from_string(_CSS)
        else:
            provider.load_from_data(_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # Run from a checkout, the icon is not installed: take it from data/
        icons = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        theme = Gtk.IconTheme.get_for_display(display)
        if not theme.has_icon(__app_id__) and os.path.isfile(os.path.join(icons, f"{__app_id__}.svg")):
            theme.add_search_path(icons)

    def _on_activate(self, app):
        self._get_or_create_window().present()

    def _on_quit(self, action, param):
        for window in list(self.get_windows()):
            window.close()

    def _on_open(self, app, files, n_files, hint):
        window = self._get_or_create_window()
        window.present()
        for gfile in files:
            path = gfile.get_path()  # None for non-local URIs
            if path:
                window.open_path(path)

    def _get_or_create_window(self) -> MarkerWindow:
        """The app's window. A new one picks up where the last run left off,
        also when files were named on the command line: they open on top of
        the restored session, which is saved again when the window closes."""
        for window in self.get_windows():
            if isinstance(window, MarkerWindow):
                return window
        window = MarkerWindow(application=self)
        window.restore_documents()
        return window

    def _on_about(self, action, param):
        about = Gtk.AboutDialog(
            transient_for=self.get_active_window(),
            modal=True,
            program_name="Marker",
            logo_icon_name=__app_id__,
            version=__version__,
            comments="Markdown and TXT viewer/editor for Linux",
            license_type=Gtk.License.GPL_3_0,
            authors=["Daniel"],
        )
        about.present()
