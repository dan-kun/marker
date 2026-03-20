"""File explorer sidebar with lazy-loaded directory tree."""

import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GObject, GLib, Pango


# File extensions shown in the explorer
SHOWN_EXTENSIONS = {
    ".md", ".markdown", ".mkd", ".mdown",
    ".txt", ".rst", ".log", ".csv",
    ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf",
    ".py", ".js", ".ts", ".sh", ".html", ".css",
}


class FileNode(GObject.Object):
    """Represents a file or directory in the tree."""

    def __init__(self, path: str, is_dir: bool):
        super().__init__()
        self.path = path
        self.is_dir = is_dir
        self.name = os.path.basename(path) or path

    @property
    def icon_name(self) -> str:
        if self.is_dir:
            return "folder-symbolic"
        ext = os.path.splitext(self.name)[1].lower()
        if ext in {".md", ".markdown", ".mkd"}:
            return "text-x-markdown-symbolic"
        return "text-x-generic-symbolic"


class FileExplorer(Gtk.Box):
    """Sidebar widget showing a file tree for a directory."""

    __gsignals__ = {
        "file-activated": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(220, -1)

        self._root_path: str | None = None
        self._file_monitor: Gio.FileMonitor | None = None

        self._build_ui()

    def _build_ui(self):
        # Header with root path label + open folder button
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

        # Scrolled list
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
        if path == self._root_path:
            return

        self._root_path = path
        self._root_label.set_text(os.path.basename(path) or path)
        self._root_label.set_tooltip_text(path)
        self._refresh()
        self._setup_monitor(path)

    def _setup_monitor(self, path: str):
        if self._file_monitor:
            self._file_monitor.cancel()
        gfile = Gio.File.new_for_path(path)
        try:
            self._file_monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._file_monitor.connect("changed", self._on_dir_changed)
        except Exception:
            pass

    def _on_dir_changed(self, monitor, gfile, other, event):
        # Debounce refresh
        GLib.timeout_add(200, self._refresh)

    def _refresh(self):
        # Clear existing rows
        while True:
            row = self._list_box.get_row_at_index(0)
            if row is None:
                break
            self._list_box.remove(row)

        if not self._root_path:
            return False

        self._populate_dir(self._root_path, depth=0)
        return False  # Don't repeat the timeout

    def _populate_dir(self, path: str, depth: int, max_depth: int = 3):
        """Recursively populate the list with files up to max_depth."""
        if depth > max_depth:
            return
        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            name = entry.name
            if name.startswith("."):
                continue  # skip hidden

            if entry.is_dir(follow_symlinks=False):
                row = self._make_row(entry.path, name, depth, is_dir=True)
                self._list_box.append(row)
            elif entry.is_file():
                ext = os.path.splitext(name)[1].lower()
                if ext in SHOWN_EXTENSIONS:
                    row = self._make_row(entry.path, name, depth, is_dir=False)
                    self._list_box.append(row)

    def _make_row(self, path: str, name: str, depth: int, is_dir: bool) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.path = path  # type: ignore[attr-defined]
        row.is_dir = is_dir  # type: ignore[attr-defined]
        row.expanded = False  # type: ignore[attr-defined]
        row.depth = depth  # type: ignore[attr-defined]

        box = Gtk.Box(spacing=6)
        box.set_margin_start(8 + depth * 16)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        if is_dir:
            icon_name = "folder-symbolic"
        else:
            icon_name = self._get_file_icon(name)

        icon = Gtk.Image.new_from_icon_name(icon_name)
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

    def _get_file_icon(self, name: str) -> str:
        ext = os.path.splitext(name)[1].lower()
        if ext in {".md", ".markdown", ".mkd"}:
            return "text-x-markdown-symbolic"
        if ext in {".py"}:
            return "text-x-python-symbolic"
        if ext in {".json", ".yaml", ".yml", ".toml"}:
            return "text-x-script-symbolic"
        return "text-x-generic-symbolic"

    def _on_row_activated(self, listbox, row):
        if row is None:
            return
        path = row.path
        is_dir = row.is_dir

        if is_dir:
            self._toggle_dir(row)
        else:
            self.emit("file-activated", path)

    def _toggle_dir(self, dir_row):
        """Expand or collapse a directory row inline."""
        if not dir_row.expanded:
            self._expand_dir(dir_row)
        else:
            self._collapse_dir(dir_row)

    def _expand_dir(self, dir_row):
        dir_row.expanded = True
        if hasattr(dir_row, "arrow"):
            dir_row.arrow.set_from_icon_name("go-down-symbolic")

        # Find insertion index
        index = dir_row.get_index() + 1
        depth = dir_row.depth + 1

        try:
            entries = sorted(os.scandir(dir_row.path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            name = entry.name
            if name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                row = self._make_row(entry.path, name, depth, is_dir=True)
                row.parent_dir_row = dir_row  # type: ignore[attr-defined]
                self._list_box.insert(row, index)
                index += 1
            elif entry.is_file():
                ext = os.path.splitext(name)[1].lower()
                if ext in SHOWN_EXTENSIONS:
                    row = self._make_row(entry.path, name, depth, is_dir=False)
                    row.parent_dir_row = dir_row  # type: ignore[attr-defined]
                    self._list_box.insert(row, index)
                    index += 1

    def _collapse_dir(self, dir_row):
        dir_row.expanded = False
        if hasattr(dir_row, "arrow"):
            dir_row.arrow.set_from_icon_name("go-next-symbolic")

        # Remove all children (recursively) that belong to this dir_row
        to_remove = []
        row = self._list_box.get_row_at_index(dir_row.get_index() + 1)
        while row is not None:
            if not hasattr(row, "parent_dir_row"):
                break
            if not self._is_descendant_of(row, dir_row):
                break
            to_remove.append(row)
            row = self._list_box.get_row_at_index(dir_row.get_index() + 1 + len(to_remove))

        for r in to_remove:
            self._list_box.remove(r)

    def _is_descendant_of(self, row, ancestor_row) -> bool:
        """Check if row is a direct or indirect child of ancestor_row."""
        current = row
        while hasattr(current, "parent_dir_row"):
            if current.parent_dir_row is ancestor_row:
                return True
            current = current.parent_dir_row
        return False

    def _on_open_folder_clicked(self, btn):
        dialog = Gtk.FileDialog(title="Open Folder")
        # Get the window from parent hierarchy
        parent = self.get_root()
        dialog.select_folder(parent, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            gfile = dialog.select_folder_finish(result)
        except Exception:
            return
        if gfile:
            self.set_root(gfile.get_path())
