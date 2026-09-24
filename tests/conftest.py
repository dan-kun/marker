"""Test setup: isolated config dir, GTK stack, and helpers to drive the app.

GUI tests need a display; run them under Xvfb:
    xvfb-run -a python3 -m pytest
"""

import os
import tempfile
import time

import pytest

# Must happen before GLib caches the user dirs.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="marker-test-config-")
os.environ.setdefault("GTK_A11Y", "none")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")
gi.require_version("WebKit", "6.0")

from gi.repository import GLib, Gtk  # noqa: E402

HAS_DISPLAY = Gtk.init_check() if hasattr(Gtk, "init_check") else True

needs_display = pytest.mark.skipif(not HAS_DISPLAY, reason="needs a display (use xvfb-run)")


def iterate(seconds: float = 0.0):
    """Run the main loop until idle, or for at least `seconds`."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + seconds
    while True:
        while context.iteration(False):
            pass
        if time.monotonic() >= deadline:
            return
        time.sleep(0.01)


def wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        iterate()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def dialogs_log(monkeypatch):
    """Record every message dialog the app shows (newest last)."""
    from marker import dialogs

    shown = []
    original = dialogs.MessageDialog.present

    def present(self):
        shown.append(self)
        return original(self)

    monkeypatch.setattr(dialogs.MessageDialog, "present", present)
    return shown


@pytest.fixture
def save_as(monkeypatch):
    """Replace the Save As file chooser. Set .path to the answer (None = cancel);
    set .defer = True to answer later with .answer()."""
    from marker import dialogs

    class FakeChooser:
        path = None
        defer = False
        pending = None
        calls = 0

        def __call__(self, parent, on_chosen, name=None, folder=None):
            self.calls += 1
            if self.defer:
                self.pending = on_chosen
            else:
                on_chosen(self.path)

        def answer(self, path):
            callback, self.pending = self.pending, None
            callback(path)

    fake = FakeChooser()
    monkeypatch.setattr(dialogs, "choose_save_path", fake)
    return fake


@pytest.fixture(scope="session")
def app():
    from marker.application import MarkerApplication

    application = MarkerApplication()
    application.register(None)
    return application


@pytest.fixture
def window(app):
    from marker.window import MarkerWindow

    win = MarkerWindow(application=app)
    win.present()
    iterate(0.2)
    yield win
    for tab in win.tab_manager.tabs():
        tab.file_manager._buffer.set_modified(False)
    win.close()
    iterate(0.1)
