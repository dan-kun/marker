"""Marker GTK4 Application."""

import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GLib
from .window import MarkerWindow
from . import __app_id__, __version__


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
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def _on_activate(self, app):
        window = self._get_or_create_window()
        window.present()

    def _on_open(self, app, files, n_files, hint):
        window = self._get_or_create_window()
        window.present()
        if files:
            window.open_file(files[0].get_path())

    def _get_or_create_window(self):
        windows = self.get_windows()
        if windows:
            return windows[0]
        window = MarkerWindow(application=self)
        return window

    def _on_about(self, action, param):
        about = Gtk.AboutDialog(
            transient_for=self.get_active_window(),
            modal=True,
            program_name="Marker",
            logo_icon_name="marker",
            version=__version__,
            comments="Markdown and TXT viewer/editor for Linux",
            license_type=Gtk.License.GPL_3_0,
            authors=["Daniel"],
        )
        about.present()
