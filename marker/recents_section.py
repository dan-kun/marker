"""Sidebar 'RECENT' collapsible section widget."""

import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, Pango

from .recents import RecentFilesManager, SIDEBAR_LIMIT, format_relative_time


class RecentsSection(Gtk.Box):
    """Collapsible recent-files section shown above the file tree in the sidebar."""

    __gsignals__ = {
        "file-activated": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, recents_manager: RecentFilesManager):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._manager = recents_manager
        self._expanded = True
        self._build_ui()
        self._manager.connect("changed", lambda _: self._refresh())
        self._refresh()

    def _build_ui(self):
        header = Gtk.Box(spacing=4)
        header.set_margin_start(8)
        header.set_margin_end(8)
        header.set_margin_top(6)
        header.set_margin_bottom(2)

        self._arrow = Gtk.Image.new_from_icon_name("go-down-symbolic")
        self._arrow.set_pixel_size(10)
        header.append(self._arrow)

        title = Gtk.Label(label="RECENT", xalign=0)
        title.add_css_class("caption")
        title.add_css_class("dim-label")
        title.set_hexpand(True)
        header.append(title)

        gesture = Gtk.GestureClick()
        gesture.connect("released", self._on_header_clicked)
        header.add_controller(gesture)

        self.append(header)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.connect("row-activated", self._on_row_activated)
        self.append(self._list_box)

        self.append(Gtk.Separator())

    def _on_header_clicked(self, gesture, n_press, x, y):
        self._expanded = not self._expanded
        self._list_box.set_visible(self._expanded)
        self._arrow.set_from_icon_name(
            "go-down-symbolic" if self._expanded else "go-next-symbolic"
        )

    def _refresh(self):
        while (row := self._list_box.get_row_at_index(0)) is not None:
            self._list_box.remove(row)

        recents = self._manager.get_recents(limit=SIDEBAR_LIMIT)
        self.set_visible(bool(recents))
        for entry in recents:
            self._list_box.append(self._make_row(entry["path"], entry["opened_at"]))

    def _make_row(self, path: str, opened_at: float) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.path = path  # type: ignore[attr-defined]

        box = Gtk.Box(spacing=6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(3)
        box.set_margin_bottom(3)

        icon = Gtk.Image.new_from_icon_name("text-x-generic-symbolic")
        icon.set_pixel_size(16)
        box.append(icon)

        label = Gtk.Label(label=os.path.basename(path), xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        box.append(label)

        time_label = Gtk.Label(label=format_relative_time(opened_at), xalign=1)
        time_label.add_css_class("caption")
        time_label.add_css_class("dim-label")
        box.append(time_label)

        row.set_child(box)
        return row

    def _on_row_activated(self, listbox, row):
        if row is not None:
            self.emit("file-activated", row.path)
