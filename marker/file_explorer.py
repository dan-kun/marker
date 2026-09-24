"""File explorer sidebar with lazily expanded directory rows."""

import os

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GObject, Gtk, Pango

from . import dialogs
from .filetypes import icon_name, is_shown
from .utils import Debouncer


def list_entries(path: str) -> list[tuple[str, str, bool]]:
    """Visible (name, full path, is_dir) entries of a folder: directories
    first, then shown files, each sorted case-insensitively."""
    try:
        with os.scandir(path) as it:
            entries = []
            for entry in it:
                if entry.name.startswith("."):
                    continue
                try:
                    is_dir = entry.is_dir()
                    if not is_dir and not (entry.is_file() and is_shown(entry.name)):
                        continue
                except OSError:
                    continue  # broken symlink or vanished entry
                entries.append((entry.name, entry.path, is_dir))
    except OSError:
        return []
    entries.sort(key=lambda e: (not e[2], e[0].lower()))
    return entries


class FileExplorer(Gtk.Box):
    """Sidebar widget showing a file tree for a directory."""

    __gsignals__ = {
        "file-activated": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(220, -1)

        self._root_path: str | None = None
        self._expanded: set[str] = set()
        self._monitors: dict[str, Gio.FileMonitor] = {}
        self._refresh_later = Debouncer(250, self._refresh)

        self._build_ui()

    @property
    def root_path(self) -> str | None:
        return self._root_path

    def _build_ui(self):
        header = Gtk.Box(spacing=4)
        header.set_margin_start(8)
        header.set_margin_end(4)
        header.set_margin_top(6)
        header.set_margin_bottom(4)

        self._root_label = Gtk.Label(
            label="No folder open",
            xalign=0,
            ellipsize=Pango.EllipsizeMode.START,
        )
        self._root_label.set_hexpand(True)
        self._root_label.add_css_class("caption")
        self._root_label.add_css_class("dim-label")
        header.append(self._root_label)

        btn_open = Gtk.Button(icon_name="folder-open-symbolic", tooltip_text="Open folder")
        btn_open.add_css_class("flat")
        btn_open.add_css_class("circular")
        btn_open.connect("clicked", self._on_open_folder_clicked)
        header.append(btn_open)

        self.append(header)
        self.append(Gtk.Separator())

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.connect("row-activated", self._on_row_activated)
        scrolled.set_child(self._list_box)

        self.append(scrolled)

    def set_root(self, path: str):
        """Set the root directory for the explorer."""
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        path = os.path.abspath(path)
        if path == self._root_path:
            return

        self._root_path = path
        self._expanded.clear()
        self._root_label.set_text(os.path.basename(path) or path)
        self._root_label.set_tooltip_text(path)
        self._refresh()

    # ── Monitoring ─────────────────────────────────────────────────────────

    def _sync_monitors(self):
        """Watch the root and every expanded folder, nothing else."""
        wanted = {self._root_path, *self._expanded} if self._root_path else set()
        for path in list(self._monitors):
            if path not in wanted:
                self._monitors.pop(path).cancel()
        for path in wanted - self._monitors.keys():
            try:
                monitor = Gio.File.new_for_path(path).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            except Exception:
                continue
            monitor.connect("changed", lambda *_: self._refresh_later.trigger())
            self._monitors[path] = monitor

    # ── Tree ───────────────────────────────────────────────────────────────

    def _refresh(self):
        """Rebuild the rows, keeping expanded folders expanded."""
        while (row := self._list_box.get_row_at_index(0)) is not None:
            self._list_box.remove(row)

        if self._root_path:
            if not os.path.isdir(self._root_path):
                self._root_label.set_text("Folder not found")
            self._expanded = {p for p in self._expanded if os.path.isdir(p)}
            self._insert_children(self._root_path, index=0, depth=0)
        self._sync_monitors()

    def _insert_children(self, folder: str, index: int, depth: int) -> int:
        """Insert rows for folder's entries at index; returns the next index."""
        for name, path, is_dir in list_entries(folder):
            row = self._make_row(path, name, depth, is_dir)
            self._list_box.insert(row, index)
            index += 1
            if is_dir and path in self._expanded:
                self._set_arrow(row, expanded=True)
                index = self._insert_children(path, index, depth + 1)
        return index

    def _make_row(self, path: str, name: str, depth: int, is_dir: bool) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.path = path  # type: ignore[attr-defined]
        row.is_dir = is_dir  # type: ignore[attr-defined]
        row.depth = depth  # type: ignore[attr-defined]
        row.set_tooltip_text(path)

        box = Gtk.Box(spacing=6)
        box.set_margin_start(8 + depth * 16)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        icon = Gtk.Image.new_from_icon_name("folder-symbolic" if is_dir else icon_name(name))
        icon.set_pixel_size(16)
        box.append(icon)

        label = Gtk.Label(label=name, xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        box.append(label)

        if is_dir:
            arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
            arrow.set_pixel_size(12)
            arrow.add_css_class("dim-label")
            row.arrow = arrow  # type: ignore[attr-defined]
            box.append(arrow)

        row.set_child(box)
        return row

    @staticmethod
    def _set_arrow(row, expanded: bool):
        row.arrow.set_from_icon_name("go-down-symbolic" if expanded else "go-next-symbolic")

    def _on_row_activated(self, listbox, row):
        if row is None:
            return
        if row.is_dir:
            self._toggle_dir(row)
        else:
            self.emit("file-activated", row.path)

    def _toggle_dir(self, dir_row):
        if dir_row.path in self._expanded:
            self._collapse_dir(dir_row)
        else:
            self._expand_dir(dir_row)
        self._sync_monitors()

    def _expand_dir(self, dir_row):
        self._expanded.add(dir_row.path)
        self._set_arrow(dir_row, expanded=True)
        self._insert_children(dir_row.path, dir_row.get_index() + 1, dir_row.depth + 1)

    def _collapse_dir(self, dir_row):
        self._set_arrow(dir_row, expanded=False)
        prefix = dir_row.path + os.sep
        self._expanded = {p for p in self._expanded if p != dir_row.path and not p.startswith(prefix)}

        # Children follow their folder and are indented deeper
        index = dir_row.get_index() + 1
        while (row := self._list_box.get_row_at_index(index)) is not None and row.depth > dir_row.depth:
            self._list_box.remove(row)

    def _on_open_folder_clicked(self, btn):
        dialogs.choose_folder(self.get_root(), self.set_root)
