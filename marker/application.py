"""Marker GTK4 Application."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from . import __app_id__, __version__
from .window import MarkerWindow


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

    def _on_activate(self, app):
        window = self._get_or_create_window()
        window.present()

    def _on_quit(self, action, param):
        for window in list(self.get_windows()):
            window.close()

    def _on_open(self, app, files, n_files, hint):
        window = self._get_or_create_window()
        window.present()
        for gfile in files:
            path = gfile.get_path()  # None for non-local URIs
            if path:
                window.open_file(path)

    def _get_or_create_window(self) -> MarkerWindow:
        for window in self.get_windows():
            if isinstance(window, MarkerWindow):
                return window
        return MarkerWindow(application=self)

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
