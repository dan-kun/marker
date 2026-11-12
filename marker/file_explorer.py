"""File explorer sidebar: a workspace of one or more folders, with lazily
expanded directory rows."""

import difflib
import os
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, GObject, Gtk, Pango

from . import dialogs
from .filetypes import icon_name, is_shown
from .titles import display, short_labels
from .utils import Debouncer

# Above this many row comparisons, a changed stretch of the tree is replaced
# whole instead of being compared row by row
_DIFF_LIMIT = 100_000_000


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


@dataclass(frozen=True)
class Entry:
    """What one row of the tree shows."""

    path: str
    name: str
    depth: int
    is_dir: bool
    is_root: bool = False


class FileRow(Gtk.ListBoxRow):
    """One file or folder in the tree. A workspace folder (root) is a row at
    depth 0 with a button to remove it from the workspace."""

    def __init__(self, entry: Entry, on_remove=None):
        super().__init__()
        self.entry = entry
        self.path = entry.path
        self.is_dir = entry.is_dir
        self.depth = entry.depth
        self.is_root = entry.is_root
        self._arrow: Gtk.Image | None = None
        self.set_tooltip_text(display(entry.path))

        box = Gtk.Box(spacing=6)
        box.set_margin_start(8 + max(0, entry.depth - 1) * 16 if not self.is_root else 4)
        box.set_margin_end(4 if self.is_root else 8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        if entry.is_dir:
            self._arrow = Gtk.Image.new_from_icon_name("pan-end-symbolic")
            self._arrow.set_pixel_size(12)
            self._arrow.add_css_class("dim-label")
            box.append(self._arrow)
        else:
            spacer = Gtk.Box()  # keeps file icons aligned with folder icons
            spacer.set_size_request(12, -1)
            box.append(spacer)

        icon = Gtk.Image.new_from_icon_name(
            "folder-symbolic" if entry.is_dir else icon_name(entry.name)
        )
        icon.set_pixel_size(16)
        box.append(icon)

        # A name that is not valid UTF-8 cannot be a label as it is
        label = Gtk.Label(label=display(entry.name), xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE if self.is_root else Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        if self.is_root:
            label.add_css_class("heading")
        box.append(label)

        if self.is_root and on_remove is not None:
            remove = Gtk.Button(icon_name="window-close-symbolic",
                                tooltip_text="Remove folder from the sidebar")
            remove.add_css_class("flat")
            remove.add_css_class("circular")
            remove.set_valign(Gtk.Align.CENTER)
            remove.connect("clicked", lambda *_: on_remove(entry.path))
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


def _folders_between(root: str, folder: str) -> set[str]:
    """folder and its parents, up to and including root."""
    folders = set()
    while _is_within(folder, root):
        folders.add(folder)
        if folder == root:
            break
        folder = os.path.dirname(folder)
    return folders


class FileExplorer(Gtk.Box):
    """Sidebar tree of the workspace: one or more folders shown together."""

    __gsignals__ = {
        "file-activated": (GObject.SignalFlags.RUN_LAST, None, (object,)),
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
        title.add_css_class("marker-dim")
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
        placeholder.add_css_class("marker-dim")
        placeholder.set_margin_top(24)
        placeholder.set_margin_start(12)
        placeholder.set_margin_end(12)
        self._list_box.set_placeholder(placeholder)

        self._scrolled.set_child(self._list_box)
        self.append(self._scrolled)

    # ── Workspace folders ──────────────────────────────────────────────────
    # No workspace folder lies inside another: the inner one would show its
    # files twice, with two rows fighting over the same expanded state.

    @property
    def roots(self) -> list[str]:
        """The workspace folders, in display order."""
        return list(self._roots)

    def shows(self, path: str) -> bool:
        """Whether path is inside one of the workspace folders."""
        return self._root_of(path) is not None

    def _root_of(self, path: str) -> str | None:
        """The workspace folder that contains path."""
        path = os.path.abspath(path)
        return next((root for root in self._roots if _is_within(path, root)), None)

    def add_root(self, path: str):
        """Add a folder to the workspace. One that is already shown inside
        another folder is opened there instead, and one that contains
        folders of the workspace takes their place."""
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        path = os.path.abspath(path)
        if path in self._roots:
            return
        parent = self._root_of(path)
        if parent is not None:
            self._expanded |= _folders_between(parent, path)
            self._refresh()
            return
        inside = [root for root in self._roots if _is_within(root, path)]
        for root in inside:  # what was visible stays visible, under the new folder
            self._expanded |= _folders_between(path, root)
        position = self._roots.index(inside[0]) if inside else len(self._roots)
        self._roots = [root for root in self._roots if root not in inside]
        self._roots.insert(position, path)
        self._expanded.add(path)
        self._refresh()
        self.emit("roots-changed")

    def remove_root(self, path: str):
        if path not in self._roots:
            return
        self._roots.remove(path)
        self._expanded = {p for p in self._expanded if not _is_within(p, path)}
        self._refresh()
        self.emit("roots-changed")

    def set_roots(self, paths: list[str]):
        """Replace the workspace with these folders."""
        folders = list(dict.fromkeys(os.path.abspath(p) for p in paths if os.path.isdir(p)))
        roots = [folder for folder in folders
                 if not any(other != folder and _is_within(folder, other) for other in folders)]
        if roots == self._roots:
            return
        self._roots = roots
        self._expanded = set(roots)
        self._refresh()
        self.emit("roots-changed")

    def reveal(self, path: str | None, expand: bool = True):
        """Select path's row. With expand, the folders that lead to it are
        opened first; without, a file inside a collapsed folder is simply
        not selected. Does nothing visible for a file outside the workspace."""
        target = os.path.abspath(path) if path else None
        self._revealed = target
        root = self._root_of(target) if target else None
        if target is not None and root is not None and expand:
            ancestors = _folders_between(root, os.path.dirname(target))
            if not ancestors <= self._expanded:
                self._expanded |= ancestors
                self._refresh()
        self._select_revealed(scroll=True)

    def _rows(self) -> list[FileRow]:
        rows = []
        index = 0
        while (row := self._list_box.get_row_at_index(index)) is not None:
            if isinstance(row, FileRow):
                rows.append(row)
            index += 1
        return rows

    def _select_revealed(self, scroll: bool = False):
        for row in self._rows():
            if row.path == self._revealed and not row.is_dir:
                self._list_box.select_row(row)
                if scroll:
                    GLib.idle_add(self._scroll_to_row, row)
                return
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

    def _entries(self) -> list[Entry]:
        """Every row the tree should show now, top to bottom."""
        entries: list[Entry] = []

        def add_children(folder: str, depth: int):
            for name, path, is_dir in list_entries(folder):
                entries.append(Entry(path, name, depth, is_dir))
                if is_dir and path in self._expanded:
                    add_children(path, depth + 1)

        names = short_labels(self._roots)
        for root in self._roots:
            entries.append(Entry(root, names[root], 0, True, is_root=True))
            if root in self._expanded:
                add_children(root, 1)
        return entries

    def _refresh(self):
        """Bring the rows in line with the folders on disk.

        Only the rows that differ are replaced. Most refreshes change
        nothing (saving a file is enough to trigger one), and rebuilding a
        big tree takes long enough to notice, loses the selection and
        jumps back to the top.
        """
        gone = [root for root in self._roots if not os.path.isdir(root)]
        if gone:  # deleted, renamed or unmounted while it was showing
            self._roots = [root for root in self._roots if root not in gone]
        self._expanded = {p for p in self._expanded if os.path.isdir(p) and self.shows(p)}

        rows = self._rows()
        entries = self._entries()
        selected = self._list_box.get_selected_row()
        selected_path = selected.path if isinstance(selected, FileRow) else None

        # Rows that already match at the top and at the bottom stay, and
        # what lies between is compared in detail
        keep_top = 0
        while keep_top < min(len(rows), len(entries)) and rows[keep_top].entry == entries[keep_top]:
            keep_top += 1
        keep_bottom = 0
        while keep_bottom < min(len(rows), len(entries)) - keep_top \
                and rows[-1 - keep_bottom].entry == entries[-1 - keep_bottom]:
            keep_bottom += 1
        old = rows[keep_top:len(rows) - keep_bottom]
        new = entries[keep_top:len(entries) - keep_bottom]
        if len(old) * len(new) <= _DIFF_LIMIT:
            matcher = difflib.SequenceMatcher(None, [row.entry for row in old], new, autojunk=False)
            changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
        else:
            changes = [("replace", 0, len(old), 0, len(new))]

        for _, old_start, old_end, _, _ in changes:
            for row in old[old_start:old_end]:
                self._list_box.remove(row)
        for _, _, _, new_start, new_end in changes:  # in order, so indexes are final
            for index in range(new_start, new_end):
                self._list_box.insert(FileRow(new[index], on_remove=self.remove_root), keep_top + index)

        rows = self._rows()
        for row in rows:
            if row.is_dir:
                row.set_expanded(row.path in self._expanded)
        self._sync_monitors()

        if self._list_box.get_selected_row() is None:
            # The selected row was replaced: select its successor, or the
            # open document if its row has just appeared
            wanted = selected_path or self._revealed
            for row in rows:
                if row.path == wanted and (wanted == selected_path or not row.is_dir):
                    self._list_box.select_row(row)
                    break
        if gone:
            self.emit("roots-changed")

    def _on_row_activated(self, listbox, row):
        if not isinstance(row, FileRow):
            return
        if not row.is_dir:
            self.emit("file-activated", row.path)
        elif row.path in self._expanded:
            # Folders inside it are closed too: reopening it shows one level
            self._expanded = {p for p in self._expanded if not _is_within(p, row.path)}
            self._refresh()
        else:
            self._expanded.add(row.path)
            self._refresh()

    def _on_add_folder_clicked(self, btn):
        dialogs.choose_folder(self.get_root(), self.add_root)
