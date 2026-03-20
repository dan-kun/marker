"""Keyboard shortcuts overlay window."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk


class ShortcutsWindow(Gtk.ShortcutsWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build()

    def _build(self):
        section = Gtk.ShortcutsSection(section_name="shortcuts", title="Shortcuts")

        def group(title, *shortcuts):
            g = Gtk.ShortcutsGroup(title=title)
            for accel, desc in shortcuts:
                s = Gtk.ShortcutsShortcut(accelerator=accel, title=desc)
                g.append(s)
            section.append(g)

        group(
            "Files",
            ("<Ctrl>n", "New file"),
            ("<Ctrl>o", "Open file"),
            ("<Ctrl>s", "Save"),
            ("<Ctrl><Shift>s", "Save as"),
            ("<Ctrl>w", "Close file"),
        )
        group(
            "View",
            ("<Ctrl>e", "Toggle split view"),
            ("<Ctrl><Shift>p", "Preview only"),
            ("<Ctrl>backslash", "Toggle sidebar"),
            ("F11", "Fullscreen"),
            ("<Ctrl>plus", "Zoom in"),
            ("<Ctrl>minus", "Zoom out"),
            ("<Ctrl>0", "Reset zoom"),
        )
        group(
            "Editing",
            ("<Ctrl>z", "Undo"),
            ("<Ctrl><Shift>z", "Redo"),
            ("<Ctrl>g", "Go to line"),
        )
        group(
            "Search",
            ("<Ctrl>f", "Find in file"),
            ("<Ctrl>h", "Find and replace"),
            ("<Ctrl><Shift>f", "Search in directory"),
        )
        group(
            "Application",
            ("<Ctrl>comma", "Preferences"),
            ("<Ctrl>q", "Quit"),
        )

        self.append(section)
