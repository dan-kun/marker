"""Keyboard shortcuts dialog."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Pango


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
        ("Ctrl++", "Zoom in"),
        ("Ctrl+-", "Zoom out"),
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
            default_width=480,
            default_height=540,
            resizable=False,
            **kwargs,
        )
        self._build()

    def _build(self):
        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        outer.set_margin_start(32)
        outer.set_margin_end(32)
        outer.set_margin_top(24)
        outer.set_margin_bottom(24)

        for group_title, shortcuts in _SHORTCUTS:
            # Group heading
            heading = Gtk.Label(label=group_title, xalign=0)
            heading.add_css_class("title-4")
            outer.append(heading)

            grid = Gtk.Grid(column_spacing=24, row_spacing=6)
            grid.set_margin_start(8)

            for row, (accel, desc) in enumerate(shortcuts):
                # Accelerator badge
                accel_label = Gtk.Label(label=accel, xalign=1)
                accel_label.add_css_class("monospace")
                accel_label.add_css_class("caption")
                accel_label.set_hexpand(False)
                accel_label.set_width_chars(18)

                # Description
                desc_label = Gtk.Label(label=desc, xalign=0)
                desc_label.set_hexpand(True)

                grid.attach(accel_label, 0, row, 1, 1)
                grid.attach(desc_label, 1, row, 1, 1)

            outer.append(grid)
            outer.append(Gtk.Separator())

        scrolled.set_child(outer)

        # Header bar
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(scrolled)
        self.set_child(box)
