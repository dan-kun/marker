"""File explorer sidebar: a workspace of one or more folders, with lazily
expanded directory rows."""

import os

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, GObject, Gtk, Pango

from . import dialogs
from .filetypes import icon_name, is_shown
from .titles import short_labels
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


class FileRow(Gtk.ListBoxRow):
    """One file or folder in the tree. A workspace folder (root) is a row at
    depth 0 with a button to remove it from the workspace."""

    def __init__(self, path: str, name: str, depth: int, is_dir: bool, on_remove=None):
        super().__init__()
        self.path = path
        self.is_dir = is_dir
        self.depth = depth
        self.is_root = on_remove is not None
        self._arrow: Gtk.Image | None = None
        self.set_tooltip_text(path)

        box = Gtk.Box(spacing=6)
        box.set_margin_start(8 + max(0, depth - 1) * 16 if not self.is_root else 4)
        box.set_margin_end(4 if self.is_root else 8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        if is_dir:
            self._arrow = Gtk.Image.new_from_icon_name("pan-end-symbolic")
            self._arrow.set_pixel_size(12)
            self._arrow.add_css_class("dim-label")
            box.append(self._arrow)
        else:
            spacer = Gtk.Box()  # keeps file icons aligned with folder icons
            spacer.set_size_request(12, -1)
            box.append(spacer)

        icon = Gtk.Image.new_from_icon_name("folder-symbolic" if is_dir else icon_name(name))
        icon.set_pixel_size(16)
        box.append(icon)

        label = Gtk.Label(label=name, xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE if self.is_root else Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        if self.is_root:
            label.add_css_class("heading")
        box.append(label)

        if on_remove is not None:
            remove = Gtk.Button(icon_name="window-close-symbolic",
                                tooltip_text="Remove folder from the sidebar")
            remove.add_css_class("flat")
            remove.add_css_class("circular")
            remove.set_valign(Gtk.Align.CENTER)
            remove.connect("clicked", lambda *_: on_remove(path))
            box.append(remove)

        self.set_child(box)

    def set_expanded(self, expanded: bool):
        if self._arrow is not None:
            self._arrow.set_from_icon_name("pan-down-symbolic" if expanded else "pan-end-symbolic")


def _is_within(path: str, folder: str) -> bool:
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


class FileExplorer(Gtk.Box):
    """Sidebar tree of the workspace: one or more folders shown together."""

    __gsignals__ = {
        "file-activated": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "roots-changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(220, -1)

        self._roots: list[str] = []
        self._expanded: set[str] = set()   # folders shown open, roots included
        self._revealed: str | None = None  # file to keep selected across refreshes
        self._monitors: dict[str, Gio.FileMonitor] = {}
        self._refresh_later = Debouncer(250, self._refresh)

        self._build_ui()

    def _build_ui(self):
        header = Gtk.Box(spacing=4)
        header.set_margin_start(8)
        header.set_margin_end(4)
        header.set_margin_top(6)
        header.set_margin_bottom(2)

        title = Gtk.Label(label="FOLDERS", xalign=0)
        title.set_hexpand(True)
        title.add_css_class("caption")
        title.add_css_class("dim-label")
        header.append(title)

        btn_add = Gtk.Button(icon_name="folder-new-symbolic", tooltip_text="Add a folder to the sidebar")
        btn_add.add_css_class("flat")
        btn_add.add_css_class("circular")
        btn_add.connect("clicked", self._on_add_folder_clicked)
        header.append(btn_add)

        self.append(header)

        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.set_vexpand(True)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.connect("row-activated", self._on_row_activated)

        placeholder = Gtk.Label(
            label="No folders yet.\nAdd one with the button above, or open a file.",
            justify=Gtk.Justification.CENTER, wrap=True,
        )
        placeholder.add_css_class("dim-label")
        placeholder.set_margin_top(24)
        placeholder.set_margin_start(12)
        placeholder.set_margin_end(12)
        self._list_box.set_placeholder(placeholder)

        self._scrolled.set_child(self._list_box)
        self.append(self._scrolled)

    # ── Workspace folders ──────────────────────────────────────────────────

    @property
    def roots(self) -> list[str]:
        """The workspace folders, in display order."""
        return list(self._roots)

    def shows(self, path: str) -> bool:
        """Whether path is inside one of the workspace folders."""
        return self._root_of(path) is not None

    def _root_of(self, path: str) -> str | None:
        """The deepest workspace folder that contains path."""
        path = os.path.abspath(path)
        matches = [root for root in self._roots if _is_within(path, root)]
        return max(matches, key=len) if matches else None

    def add_root(self, path: str):
        """Add a folder to the workspace (no-op if it is already there)."""
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        path = os.path.abspath(path)
        if path in self._roots:
            return
        self._roots.append(path)
        self._expanded.add(path)
        self._refresh()
        self.emit("roots-changed")

    def remove_root(self, path: str):
        if path not in self._roots:
            return
        self._roots.remove(path)
        # Forget what was open under it, unless another root still shows it
        self._expanded = {p for p in self._expanded
                          if p != path and (not _is_within(p, path) or self._root_of(p))}
        self._refresh()
        self.emit("roots-changed")

    def set_roots(self, paths: list[str]):
        """Replace the workspace with these folders."""
        roots = list(dict.fromkeys(os.path.abspath(p) for p in paths if os.path.isdir(p)))
        if roots == self._roots:
            return
        self._roots = roots
        self._expanded = set(roots)
        self._refresh()
        self.emit("roots-changed")

    def reveal(self, path: str | None):
        """Select path's row, opening the folders that lead to it. Does
        nothing visible when the file is outside the workspace."""
        target = os.path.abspath(path) if path else None
        self._revealed = target
        root = self._root_of(target) if target else None
        if target is None or root is None:
            self._list_box.unselect_all()
            return
        ancestors = set()
        folder = os.path.dirname(target)
        while _is_within(folder, root):
            ancestors.add(folder)
            if folder == root:
                break
            folder = os.path.dirname(folder)
        if not ancestors <= self._expanded:
            self._expanded |= ancestors
            self._refresh()  # selects the row as part of rebuilding
        else:
            self._select_revealed()

    def _select_revealed(self):
        index = 0
        while (row := self._list_box.get_row_at_index(index)) is not None:
            if isinstance(row, FileRow) and row.path == self._revealed and not row.is_dir:
                self._list_box.select_row(row)
                GLib.idle_add(self._scroll_to_row, row)
                return
            index += 1
        self._list_box.unselect_all()

    def _scroll_to_row(self, row: FileRow):
        """Bring a row into view without moving keyboard focus to it."""
        if row.get_parent() is self._list_box:
            ok, bounds = row.compute_bounds(self._list_box)
            adjustment = self._scrolled.get_vadjustment()
            if ok:
                top, height = bounds.get_y(), bounds.get_height()
                page = adjustment.get_page_size()
                if top < adjustment.get_value():
                    adjustment.set_value(top)
                elif top + height > adjustment.get_value() + page:
                    adjustment.set_value(top + height - page)
        return GLib.SOURCE_REMOVE

    # ── Monitoring ─────────────────────────────────────────────────────────

    def _sync_monitors(self):
        """Watch the roots and every expanded folder, nothing else."""
        wanted = {*self._roots, *self._expanded}
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

        self._expanded = {p for p in self._expanded if os.path.isdir(p)}
        names = short_labels(self._roots)
        index = 0
        for root in self._roots:
            row = FileRow(root, names[root], 0, True, on_remove=self.remove_root)
            self._list_box.insert(row, index)
            index += 1
            if root in self._expanded:
                row.set_expanded(True)
                index = self._insert_children(root, index, depth=1)
        self._sync_monitors()
        if self._revealed:
            self._select_revealed()

    def _insert_children(self, folder: str, index: int, depth: int) -> int:
        """Insert rows for folder's entries at index; returns the next index."""
        for name, path, is_dir in list_entries(folder):
            row = FileRow(path, name, depth, is_dir)
            self._list_box.insert(row, index)
            index += 1
            if is_dir and path in self._expanded:
                row.set_expanded(True)
                index = self._insert_children(path, index, depth + 1)
        return index

    def _on_row_activated(self, listbox, row):
        if not isinstance(row, FileRow):
            return
        if row.is_dir:
            self._toggle_dir(row)
        else:
            self.emit("file-activated", row.path)

    def _toggle_dir(self, dir_row: FileRow):
        if dir_row.path in self._expanded:
            self._collapse_dir(dir_row)
        else:
            self._expand_dir(dir_row)
        self._sync_monitors()

    def _expand_dir(self, dir_row: FileRow):
        self._expanded.add(dir_row.path)
        dir_row.set_expanded(True)
        self._insert_children(dir_row.path, dir_row.get_index() + 1, dir_row.depth + 1)

    def _collapse_dir(self, dir_row: FileRow):
        dir_row.set_expanded(False)
        # A nested workspace folder keeps its own state
        self._expanded = {
            p for p in self._expanded
            if p != dir_row.path and (not _is_within(p, dir_row.path) or p in self._roots)
        }

        # Children follow their folder and are indented deeper
        index = dir_row.get_index() + 1
        while isinstance(row := self._list_box.get_row_at_index(index), FileRow) \
                and row.depth > dir_row.depth:
            self._list_box.remove(row)

    def _on_add_folder_clicked(self, btn):
        dialogs.choose_folder(self.get_root(), self.add_root)
