"""Multi-buffer tab management using Adw.TabView + Adw.TabBar."""

import os
from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GObject, Gtk

from .editor import MarkdownEditor
from .file_manager import FileManager
from .preview import MarkdownPreview
from .split_view import SplitView
from .titles import short_labels


@dataclass(slots=True, eq=False)
class TabData:
    """Per-tab widgets and the signal handlers to drop when the tab closes."""

    editor: MarkdownEditor
    split_view: SplitView
    file_manager: FileManager
    page: Adw.TabPage
    handlers: list


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


class TabManager(Gtk.Box):
    """Manages multiple editor tabs using Adw.TabView."""

    __gsignals__ = {
        "active-tab-changed": (GObject.SignalFlags.RUN_LAST, None, ()),
        # Emitted after any tab loads a file from disk
        "file-opened": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, window, recents_manager, settings):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._window = window
        self._recents_manager = recents_manager
        self._settings = settings

        # Map from Adw.TabPage → TabData
        self._tab_data: dict[Adw.TabPage, TabData] = {}

        self._tab_view = Adw.TabView()
        self._tab_view.set_vexpand(True)
        self._tab_view.set_hexpand(True)

        self._tab_bar = Adw.TabBar()
        self._tab_bar.set_view(self._tab_view)
        self._tab_bar.set_autohide(True)

        self.append(self._tab_bar)
        self.append(self._tab_view)

        # One preview for the whole window, moved into whichever tab is active
        self.preview = MarkdownPreview()
        self.preview.connect("open-file", self._on_preview_open_file)
        self.preview.connect("line-activated", self._on_preview_line_activated)
        self._preview_tab: TabData | None = None
        self._zoom = 1.0  # shared by every tab's editor and the preview

        self._tab_view.connect("notify::selected-page", self._on_selected_page_changed)
        self._tab_view.connect("close-page", self._on_close_page)
        self._settings.connect("changed", self._on_settings_changed)

        self.new_tab()

    # ── Internal helpers ───────────────────────────────────────────────────

    def _create_tab_data(self) -> TabData:
        editor = MarkdownEditor()
        editor.apply_settings(self._settings)
        editor.set_zoom(self._zoom)
        active = self._active_tab()
        # New tabs open in the view mode the user is currently working in
        split_view = SplitView(editor, mode=active.split_view.get_mode() if active else "split")
        file_manager = FileManager(self._window, editor, self._recents_manager, self._settings)

        page = self._tab_view.append(split_view)
        page.set_title("Untitled")
        page.set_tooltip("")

        tab = TabData(editor, split_view, file_manager, page, [])
        tab.handlers = [
            (file_manager, file_manager.connect("file-changed", self._on_tab_file_changed, tab)),
            (file_manager, file_manager.connect("loaded", self._on_tab_loaded)),
            (file_manager, file_manager.connect("saved", self._on_tab_saved, tab)),
        ]
        self._tab_data[page] = tab
        # Adw.TabView selects the first page as soon as it is appended,
        # before the tab is registered above, so that notify is missed.
        if self._tab_view.get_selected_page() is page:
            self._move_preview_to(tab)
        return tab

    def _update_titles(self):
        """Name each tab after its file; tabs whose files share a name also
        show the folder that tells them apart."""
        paths = [t.file_manager.current_path for t in self._tab_data.values()]
        labels = short_labels([p for p in paths if p])
        for tab in self._tab_data.values():
            path = tab.file_manager.current_path
            title = labels[path] if path else "Untitled"
            if tab.page.get_title() != title:
                tab.page.set_title(title)

    def _on_tab_file_changed(self, fm, path, is_modified, tab):
        self._update_titles()
        tab.page.set_tooltip(path)
        tab.page.set_indicator_icon(
            Gio.ThemedIcon.new("media-record-symbolic") if is_modified else None
        )
        tab.split_view.set_base_dir(os.path.dirname(path) if path else None)

    def _on_tab_loaded(self, fm, path):
        self.emit("file-opened", path)

    def _on_tab_saved(self, fm, path, tab):
        """After "Save As" onto a file that another tab has open, close that
        tab if it has nothing to lose. One with unsaved edits stays and
        reports the conflict through its own file monitor."""
        for other in self.tabs():
            other_path = other.file_manager.current_path
            if other is not tab and other_path and _same_file(other_path, path) \
                    and not other.file_manager.is_modified:
                self._tab_view.close_page(other.page)

    def _on_preview_line_activated(self, preview, line):
        tab = self._active_tab()
        if tab is not None:
            tab.editor.goto_line(line)

    def _on_preview_open_file(self, preview, path):
        self.open_file(path)

    def _on_settings_changed(self, settings, key):
        for tab in self._tab_data.values():
            tab.editor.apply_settings(settings)

    def _on_selected_page_changed(self, tab_view, param):
        self._move_preview_to(self._active_tab())
        self.emit("active-tab-changed")

    def _move_preview_to(self, tab: TabData | None):
        if tab is self._preview_tab:
            return
        if self._preview_tab is not None:
            self._preview_tab.split_view.detach_preview()
        self._preview_tab = tab
        if tab is not None:
            tab.split_view.attach_preview(self.preview)

    def _on_close_page(self, tab_view, page):
        tab = self._tab_data.get(page)
        if tab is None:
            tab_view.close_page_finish(page, True)
            return True

        def done(ok: bool):
            if ok:
                self._dispose_tab(page)
            tab_view.close_page_finish(page, ok)

        tab.file_manager.confirm_discard(done)
        return True  # we call close_page_finish() ourselves

    def _dispose_tab(self, page):
        tab = self._tab_data.pop(page, None)
        if tab is None:
            return
        for obj, handler in tab.handlers:
            obj.disconnect(handler)
        tab.handlers.clear()
        if tab is self._preview_tab:
            self._preview_tab = None
        self.preview.forget_document(tab.split_view.doc_id)
        self._update_titles()  # a remaining tab may no longer need its folder shown
        tab.file_manager.dispose()
        tab.split_view.dispose()
        tab.editor.dispose()

    def _active_tab(self) -> TabData | None:
        page = self._tab_view.get_selected_page()
        if page is None:
            return None
        return self._tab_data.get(page)

    # ── Public API ─────────────────────────────────────────────────────────

    def tabs(self) -> list[TabData]:
        """All tabs in visual order."""
        pages = (self._tab_view.get_nth_page(i) for i in range(self._tab_view.get_n_pages()))
        return [self._tab_data[p] for p in pages if p in self._tab_data]

    def modified_tabs(self) -> list[TabData]:
        return [t for t in self.tabs() if t.file_manager.is_modified]

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, level: float):
        """Zoom every editor and the preview together."""
        self._zoom = max(0.5, min(3.0, round(level, 2)))
        for tab in self._tab_data.values():
            tab.editor.set_zoom(self._zoom)
        self.preview.set_zoom(self._zoom)

    def select(self, tab: TabData):
        self._tab_view.set_selected_page(tab.page)

    def new_tab(self) -> TabData:
        tab = self._create_tab_data()
        self.select(tab)
        tab.editor.grab_focus()
        return tab

    def find_tab(self, path: str) -> TabData | None:
        for tab in self._tab_data.values():
            current = tab.file_manager.current_path
            if current and _same_file(current, path):
                return tab
        return None

    def open_file(self, path: str, create: bool = False) -> TabData | None:
        """Show path in a tab: the one already holding it, the current tab
        if it is blank, or a new tab. Returns None if the file can't be read.

        With create=True a path that does not exist yet (in an existing
        folder) opens as an empty document that is created on first save.
        """
        tab = self.find_tab(path)
        if tab is not None:
            self.select(tab)
            return tab

        active = self._active_tab()
        if active is not None and active.file_manager.is_blank:
            tab, created = active, False
        else:
            tab, created = self._create_tab_data(), True

        path = os.path.abspath(path)
        if create and not os.path.lexists(path) and os.path.isdir(os.path.dirname(path)):
            tab.file_manager.start_new(path)
        elif not tab.file_manager.load(path):
            if created:
                self._tab_view.close_page(tab.page)
            return None
        self.select(tab)
        tab.editor.grab_focus()
        return tab

    def save_all(self, tabs: list[TabData], on_done: Callable[[bool], None]):
        """Save tabs one after another; stops at the first cancel or error."""
        def step(index: int):
            if index == len(tabs):
                on_done(True)
                return
            tab = tabs[index]
            self.select(tab)
            tab.file_manager.save_file(lambda ok: step(index + 1) if ok else on_done(False))

        step(0)

    def close_active_tab(self):
        page = self._tab_view.get_selected_page()
        if page is None:
            return
        if self._tab_view.get_n_pages() <= 1:
            # Last tab: clear content instead of closing
            tab = self._tab_data.get(page)
            if tab:
                tab.file_manager.new_file()
        else:
            self._tab_view.close_page(page)

    def goto_tab(self, index: int):
        if 0 <= index < self._tab_view.get_n_pages():
            self._tab_view.set_selected_page(self._tab_view.get_nth_page(index))

    def next_tab(self):
        self._tab_view.select_next_page()

    def prev_tab(self):
        self._tab_view.select_previous_page()

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def active_tab(self) -> TabData | None:
        return self._active_tab()

    @property
    def active_editor(self) -> MarkdownEditor | None:
        tab = self._active_tab()
        return tab.editor if tab else None

    @property
    def active_split_view(self) -> SplitView | None:
        tab = self._active_tab()
        return tab.split_view if tab else None

    @property
    def active_file_manager(self) -> FileManager | None:
        tab = self._active_tab()
        return tab.file_manager if tab else None
