"""Keyboard shortcuts dialog."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw


_SHORTCUTS = [
    ("Files", [
        ("Ctrl+N", "New file"),
        ("Ctrl+O", "Open file"),
        ("Ctrl+S", "Save"),
        ("Ctrl+Shift+S", "Save as"),
        ("Ctrl+W", "Close file"),
    ]),
    ("View", [
        ("Ctrl+E", "Toggle split view"),
        ("Ctrl+Shift+P", "Preview only"),
        ("Ctrl+\\", "Toggle sidebar"),
        ("F11", "Fullscreen"),
        ("Ctrl++  /  Ctrl+-", "Zoom in / out"),
        ("Ctrl+0", "Reset zoom"),
    ]),
    ("Editing", [
        ("Ctrl+Z", "Undo"),
        ("Ctrl+Shift+Z", "Redo"),
        ("Ctrl+G", "Go to line"),
    ]),
    ("Search", [
        ("Ctrl+F", "Find in file"),
        ("Ctrl+H", "Find and replace"),
        ("Ctrl+Shift+F", "Search in directory"),
    ]),
    ("Application", [
        ("Ctrl+,", "Preferences"),
        ("Ctrl+Q", "Quit"),
    ]),
]


class ShortcutsWindow(Gtk.Window):
    def __init__(self, **kwargs):
        super().__init__(
            title="Keyboard Shortcuts",
            modal=True,
            default_width=460,
            default_height=520,
            resizable=True,
            **kwargs,
        )
        self.set_child(self._build_content())

    def _build_content(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_start(24)
        outer.set_margin_end(24)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)

        for i, (group_title, shortcuts) in enumerate(_SHORTCUTS):
            if i > 0:
                sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                sep.set_margin_top(8)
                sep.set_margin_bottom(8)
                outer.append(sep)

            heading = Gtk.Label(label=group_title, xalign=0)
            heading.add_css_class("heading")
            heading.set_margin_bottom(6)
            outer.append(heading)

            for accel, desc in shortcuts:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                row.set_margin_top(2)
                row.set_margin_bottom(2)

                desc_label = Gtk.Label(label=desc, xalign=0)
                desc_label.set_hexpand(True)
                row.append(desc_label)

                accel_label = Gtk.Label(label=accel, xalign=1)
                accel_label.add_css_class("monospace")
                accel_label.add_css_class("dim-label")
                accel_label.add_css_class("caption")
                row.append(accel_label)

                outer.append(row)

        scrolled.set_child(outer)
        return scrolled
