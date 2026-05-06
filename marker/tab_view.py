"""Multi-buffer tab management using Adw.TabView + Adw.TabBar."""

import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GObject

from .editor import MarkdownEditor
from .preview import MarkdownPreview
from .split_view import SplitView
from .file_manager import FileManager


class TabData:
    """Plain container for per-tab widgets."""

    __slots__ = ("editor", "preview", "split_view", "file_manager", "page")

    def __init__(self, editor, preview, split_view, file_manager, page):
        self.editor = editor
        self.preview = preview
        self.split_view = split_view
        self.file_manager = file_manager
        self.page = page


class TabManager(Gtk.Box):
    """Manages multiple editor tabs using Adw.TabView."""

    __gsignals__ = {
        "active-tab-changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, window, recents_manager):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._window = window
        self._recents_manager = recents_manager

        # Map from Adw.TabPage → TabData
        self._tab_data: dict = {}

        # Build the tab bar + tab view
        self._tab_view = Adw.TabView()
        self._tab_view.set_vexpand(True)
        self._tab_view.set_hexpand(True)

        self._tab_bar = Adw.TabBar()
        self._tab_bar.set_view(self._tab_view)
        self._tab_bar.set_autohide(True)

        self.append(self._tab_bar)
        self.append(self._tab_view)

        # Signals
        self._tab_view.connect("notify::selected-page", self._on_selected_page_changed)
        self._tab_view.connect("close-page", self._on_close_page)

        # Auto-hide tab bar when only one page
        self._tab_view.connect("notify::n-pages", self._on_n_pages_changed)

        # Create the initial tab
        self.new_tab()

    # ── Internal helpers ───────────────────────────────────────────────────

    def _create_tab_data(self) -> TabData:
        editor = MarkdownEditor()
        preview = MarkdownPreview()
        split_view = SplitView(editor, preview)
        split_view.set_hexpand(True)
        file_manager = FileManager(self._window, editor, self._recents_manager)

        # Wrap split_view in a simple box that will be the tab page content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.set_hexpand(True)
        content_box.set_vexpand(True)
        content_box.append(split_view)

        page = self._tab_view.append(content_box)
        page.set_title("New Document")
        page.set_tooltip("")

        tab = TabData(editor, preview, split_view, file_manager, page)
        self._tab_data[page] = tab

        # Update tab title/indicator when file changes
        file_manager.connect("file-changed", self._on_tab_file_changed, tab)

        return tab

    def _on_tab_file_changed(self, fm, path, is_modified, tab):
        page = tab.page
        if path:
            page.set_title(os.path.basename(path))
            page.set_tooltip(path)
        else:
            page.set_title("New Document")
            page.set_tooltip("")

        if is_modified:
            page.set_indicator_icon(Gio.ThemedIcon.new("media-record-symbolic"))
        else:
            page.set_indicator_icon(None)

    def _on_selected_page_changed(self, tab_view, param):
        self.emit("active-tab-changed")

    def _on_n_pages_changed(self, tab_view, param):
        n = tab_view.get_n_pages()
        self._tab_bar.set_autohide(True)

    def _on_close_page(self, tab_view, page):
        tab = self._tab_data.get(page)
        if tab is None:
            tab_view.close_page_finish(page, True)
            return

        if not tab.file_manager.is_modified:
            self._remove_tab_data(page)
            tab_view.close_page_finish(page, True)
            return

        # Unsaved changes — ask the user
        dialog = Adw.MessageDialog(
            transient_for=self._window,
            heading="Unsaved Changes",
            body="Do you want to save your changes before closing this tab?",
        )
        dialog.add_response("discard", "Discard")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response):
            if response == "save":
                tab.file_manager.save_file()
                self._remove_tab_data(page)
                tab_view.close_page_finish(page, True)
            elif response == "discard":
                self._remove_tab_data(page)
                tab_view.close_page_finish(page, True)
            else:
                tab_view.close_page_finish(page, False)

        dialog.connect("response", on_response)
        dialog.present()

    def _remove_tab_data(self, page):
        self._tab_data.pop(page, None)

    def _active_tab(self) -> TabData | None:
        page = self._tab_view.get_selected_page()
        if page is None:
            return None
        return self._tab_data.get(page)

    # ── Public API ─────────────────────────────────────────────────────────

    def new_tab(self) -> TabData:
        tab = self._create_tab_data()
        self._tab_view.set_selected_page(tab.page)
        tab.editor.grab_focus()
        return tab

    def close_active_tab(self):
        page = self._tab_view.get_selected_page()
        if page is None:
            return
        n = self._tab_view.get_n_pages()
        if n <= 1:
            # Last tab: clear content instead of closing
            tab = self._tab_data.get(page)
            if tab:
                tab.file_manager.new_file()
        else:
            self._tab_view.close_page(page)

    def goto_tab(self, index: int):
        n = self._tab_view.get_n_pages()
        if 0 <= index < n:
            page = self._tab_view.get_nth_page(index)
            self._tab_view.set_selected_page(page)

    def next_tab(self):
        self._tab_view.select_next_page()

    def prev_tab(self):
        self._tab_view.select_previous_page()

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def active_editor(self) -> MarkdownEditor | None:
        tab = self._active_tab()
        return tab.editor if tab else None

    @property
    def active_preview(self) -> MarkdownPreview | None:
        tab = self._active_tab()
        return tab.preview if tab else None

    @property
    def active_split_view(self) -> SplitView | None:
        tab = self._active_tab()
        return tab.split_view if tab else None

    @property
    def active_file_manager(self) -> FileManager | None:
        tab = self._active_tab()
        return tab.file_manager if tab else None
