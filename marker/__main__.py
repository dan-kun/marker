"""Entry point for Marker application."""

import sys

from gi.repository import GLib

from . import __app_id__


def main():
    # Matches the .desktop file name so shells can associate the window
    # with its launcher (WM_CLASS on X11).
    GLib.set_prgname(__app_id__)
    from .application import MarkerApplication

    app = MarkerApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
