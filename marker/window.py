"""Main application window for Marker."""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from . import dialogs
from .file_explorer import FileExplorer
from .filetypes import syntax_label
from .format_toolbar import FormatToolbar
from .menubar import build_menubar
from .minimap import Minimap
from .recents import MENU_LIMIT, RecentFilesManager, format_relative_time
from .recents_section import RecentsSection
from .search import SearchBar
from .settings import Settings
from .shortcuts import iter_accels
from .split_view import MODES
from .tab_view import TabManager
from .utils import Debouncer

SIDEBAR_DEFAULT_WIDTH = 240


def _is_within(path: str, folder: str) -> bool:
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


class MarkerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Marker")
        self.set_default_size(1200, 800)

        # Core components
        self.settings = Settings.get_default()
        self.recents_manager = RecentFilesManager()
        self.tab_manager = TabManager(self, self.recents_manager, self.settings)
        self.file_explorer = FileExplorer()
        self.search_bar = SearchBar(self.editor, root_provider=lambda: self.file_explorer.root_path)
        self._minimap = Minimap()

        # One Gio.Menu shared by the hamburger menu and the menubar
        self._recents_menu = Gio.Menu()

        self._tab_handlers: list = []
        self._close_confirmed = False
        self._sidebar_width = SIDEBAR_DEFAULT_WIDTH
        self._word_count = Debouncer(200, self._update_word_count)

        self._setup_actions()
        self._build_ui()
        self._setup_shortcuts()
        self._connect_signals()

        self.connect("close-request", self._on_close_request)
        self._save_tick = GLib.timeout_add_seconds(30, self._tick_save_time)

    # ── Tab-delegated properties ───────────────────────────────────────────

    @property
    def editor(self):
        return self.tab_manager.active_editor

    @property
    def preview(self):
        return self.tab_manager.active_preview

    @property
    def split_view(self):
        return self.tab_manager.active_split_view

    @property
    def file_manager(self):
        return self.tab_manager.active_file_manager

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self._header = self._build_header()
        root_box.append(self._header)

        root_box.append(build_menubar(self._recents_menu))

        root_box.append(FormatToolbar())
        root_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Content area: sidebar | main pane  (both resizable via Gtk.Paned)
        self._content_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._content_paned.set_vexpand(True)
        self._content_paned.set_hexpand(True)
        self._content_paned.set_shrink_start_child(False)
        self._content_paned.set_shrink_end_child(False)
        self._content_paned.set_resize_start_child(False)
        self._content_paned.set_resize_end_child(True)
        self._content_paned.set_position(self._sidebar_width)
        # Track manual resizes so toggling restores the right width
        self._content_paned.connect("notify::position", self._on_sidebar_paned_moved)

        self._recents_section = RecentsSection(self.recents_manager)
        self.file_explorer.set_vexpand(True)

        self._sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._sidebar_box.set_size_request(220, -1)
        self._sidebar_box.append(self._recents_section)
        self._sidebar_box.append(self.file_explorer)
        self._content_paned.set_start_child(self._sidebar_box)

        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor_box.set_hexpand(True)
        editor_box.append(self.search_bar)
        editor_box.append(self.tab_manager)
        self._content_paned.set_end_child(editor_box)

        outer_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer_hbox.set_vexpand(True)
        outer_hbox.append(self._content_paned)
        self._minimap_separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        outer_hbox.append(self._minimap_separator)
        outer_hbox.append(self._minimap)
        root_box.append(outer_hbox)

        root_box.append(self._build_statusbar())
        self.set_content(root_box)

    def _build_header(self):
        header = Adw.HeaderBar()

        left_box = Gtk.Box(spacing=4)
        for icon, tip, action in (
            ("document-new-symbolic", "New document (Ctrl+N)", "win.new-file"),
            ("document-open-symbolic", "Open file (Ctrl+O)", "win.open-file"),
            ("document-save-symbolic", "Save (Ctrl+S)", "win.save-file"),
        ):
            left_box.append(Gtk.Button(icon_name=icon, tooltip_text=tip, action_name=action))
        header.pack_start(left_box)

        right_box = Gtk.Box(spacing=4)
        right_box.append(Gtk.ToggleButton(
            icon_name="sidebar-show-symbolic",
            tooltip_text="Toggle sidebar (Ctrl+\\)",
            action_name="win.show-sidebar",
        ))

        # View mode buttons: the stateful win.view-mode action keeps them in sync
        view_box = Gtk.Box()
        view_box.add_css_class("linked")
        for mode, icon, tip in (
            ("editor", "text-editor-symbolic", "Editor only"),
            ("split", "view-dual-symbolic", "Split view (Ctrl+E)"),
            ("preview", "view-paged-symbolic", "Preview only (Ctrl+Shift+P)"),
        ):
            view_box.append(Gtk.ToggleButton(
                icon_name=icon,
                tooltip_text=tip,
                action_name="win.view-mode",
                action_target=GLib.Variant("s", mode),
            ))
        right_box.append(view_box)

        recents_section = Gio.Menu()
        recents_section.append_submenu("Open Recent", self._recents_menu)
        app_section = Gio.Menu()
        app_section.append("Preferences", "win.preferences")
        app_section.append("Keyboard Shortcuts", "win.show-shortcuts")
        app_section.append("About Marker", "app.about")
        menu = Gio.Menu()
        menu.append_section(None, recents_section)
        menu.append_section(None, app_section)
        right_box.append(Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Menu",
                                        menu_model=menu))
        header.pack_end(right_box)

        self._title_widget = Adw.WindowTitle(title="Marker", subtitle="")
        header.set_title_widget(self._title_widget)
        return header

    def _build_statusbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("statusbar")
        bar.set_margin_start(8)
        bar.set_margin_end(8)
        bar.set_margin_top(2)
        bar.set_margin_bottom(2)

        def label(text, xalign):
            widget = Gtk.Label(label=text, xalign=xalign)
            widget.add_css_class("dim-label")
            return widget

        self._status_pos = label("Ln 1, Col 1", 0)
        self._status_words = label("0 words · < 1 min read", 0)
        self._status_syntax = label("Markdown", 0)
        self._status_encoding = label("UTF-8 · LF", 1)
        self._status_save = label("", 1)

        bar.append(self._status_pos)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        bar.append(self._status_words)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        bar.append(self._status_syntax)
        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        bar.append(spacer)
        bar.append(self._status_encoding)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        bar.append(self._status_save)
        return bar

    # ── Actions ────────────────────────────────────────────────────────────

    def _add_action(self, name, callback, param_type: str | None = None):
        action = Gio.SimpleAction.new(name, GLib.VariantType.new(param_type) if param_type else None)
        action.connect("activate", callback)
        self.add_action(action)

    def _add_stateful(self, name, initial: GLib.Variant, on_change):
        param = None if initial.get_type_string() == "b" else initial.get_type()
        action = Gio.SimpleAction.new_stateful(name, param, initial)

        def change_state(act, value):
            act.set_state(value)
            on_change(value.unpack())

        action.connect("change-state", change_state)
        self.add_action(action)

    def _setup_actions(self):
        simple = {
            "new-file": self._action_new_file,
            "open-file": self._action_open_file,
            "save-file": lambda *_: self._with_tab(lambda t: t.file_manager.save_file()),
            "save-file-as": lambda *_: self._with_tab(lambda t: t.file_manager.save_file_as()),
            "close-file": lambda *_: self.tab_manager.close_active_tab(),
            "new-tab": lambda *_: self.tab_manager.new_tab(),
            "next-tab": lambda *_: self.tab_manager.next_tab(),
            "prev-tab": lambda *_: self.tab_manager.prev_tab(),
            "find": lambda *_: self.search_bar.show_search(),
            "find-replace": lambda *_: self.search_bar.show_replace(),
            "find-in-dir": lambda *_: self.search_bar.show_dir_search(),
            "toggle-split": self._action_toggle_split,
            "editor-only": lambda *_: self._set_view_mode("editor"),
            "preview-only": lambda *_: self._set_view_mode("preview"),
            "fullscreen": self._action_fullscreen,
            "zoom-in": lambda *_: self._zoom("zoom_in"),
            "zoom-out": lambda *_: self._zoom("zoom_out"),
            "zoom-reset": lambda *_: self._zoom("zoom_reset"),
            "goto-line": lambda *_: self._show_goto_line_dialog(),
            "preferences": self._action_preferences,
            "show-shortcuts": self._action_show_shortcuts,
            "clear-recents": lambda *_: self.recents_manager.clear(),
            "format-bold": lambda *_: self._with_tab(lambda t: t.editor.insert_bold()),
            "format-italic": lambda *_: self._with_tab(lambda t: t.editor.insert_italic()),
            "format-code": lambda *_: self._with_tab(lambda t: t.editor.insert_code()),
            "format-link": lambda *_: self._with_tab(lambda t: t.editor.insert_link()),
            "format-bullet-list": lambda *_: self._with_tab(lambda t: t.editor.insert_bullet_list()),
            "format-numbered-list": lambda *_: self._with_tab(lambda t: t.editor.insert_numbered_list()),
        }
        for name, callback in simple.items():
            self._add_action(name, callback)

        self._add_action("open-recent", lambda a, p: self.open_file(p.get_string()), "s")
        self._add_action("goto-tab", lambda a, p: self.tab_manager.goto_tab(p.get_int32() - 1), "i")
        self._add_action("format-heading",
                         lambda a, p: self._with_tab(lambda t: t.editor.insert_heading(p.get_int32())),
                         "i")

        # Stateful actions: buttons and menu items bound to them stay in sync.
        self._add_stateful("view-mode", GLib.Variant("s", "split"), self._on_view_mode_changed)
        self._add_stateful("show-sidebar", GLib.Variant("b", True), self._on_show_sidebar_changed)
        self._add_stateful("show-minimap", GLib.Variant("b", True), self._on_show_minimap_changed)

    def _setup_shortcuts(self):
        app = self.get_application()
        for action, accels in iter_accels():
            app.set_accels_for_action(action, accels)

    def _zoom(self, method: str):
        """Zoom the active tab's editor and preview together."""
        tab = self.tab_manager.active_tab
        if tab is not None:
            getattr(tab.editor, method)()
            getattr(tab.preview, method)()

    def _with_tab(self, func):
        tab = self.tab_manager.active_tab
        if tab is not None:
            func(tab)

    # ── Signals ────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.tab_manager.connect("active-tab-changed", lambda *_: self._connect_active_tab())
        self.tab_manager.connect("file-opened", self._on_file_opened)
        self.file_explorer.connect("file-activated", self._on_sidebar_file_activated)
        self._recents_section.connect("file-activated", self._on_sidebar_file_activated)
        self.search_bar.connect("open-location", self._on_open_location)
        self.recents_manager.connect("changed", self._rebuild_recents_menu)
        self._rebuild_recents_menu()
        self._connect_active_tab()

    def _connect_active_tab(self):
        for obj, handler in self._tab_handlers:
            obj.disconnect(handler)
        self._tab_handlers = []

        tab = self.tab_manager.active_tab
        if tab is None:
            return
        ed, fm = tab.editor, tab.file_manager
        self._tab_handlers = [
            (ed, ed.connect("cursor-moved", self._on_cursor_moved)),
            (ed, ed.connect("content-changed", lambda *_: self._word_count.trigger())),
            (fm, fm.connect("file-changed", self._on_file_changed)),
            (fm, fm.connect("saved", lambda *_: self._update_save_label())),
        ]

        # Sync UI from the new active tab's state
        self.lookup_action("view-mode").set_state(GLib.Variant("s", tab.split_view.get_mode()))
        self.search_bar.set_editor(ed)
        self._minimap.set_editor(ed)

        self._on_cursor_moved(ed, *ed.get_cursor_position())
        self._word_count.cancel()
        self._update_word_count()
        self._on_file_changed(fm, fm.current_path or "", fm.is_modified)

    def _on_cursor_moved(self, editor, line, col):
        self._status_pos.set_text(f"Ln {line}, Col {col}")

    def _update_word_count(self):
        editor = self.editor
        words = len(editor.get_text().split()) if editor else 0
        minutes = f"{max(1, round(words / 220))} min read" if words >= 110 else "< 1 min read"
        self._status_words.set_text(f"{words} {'word' if words == 1 else 'words'} · {minutes}")

    def _on_file_changed(self, fm, path, is_modified):
        name = fm.display_name if path else "Marker"
        self._title_widget.set_title(f"• {name}" if is_modified else name)
        self._title_widget.set_subtitle(path)
        self.set_title(f"{name} – Marker" if path else "Marker")
        self._status_syntax.set_text(syntax_label(path or None))
        self._status_encoding.set_text(f"{fm.encoding_label} · {fm.newline_label}")
        self._update_save_label()

    def _update_save_label(self):
        fm = self.file_manager
        if fm is None:
            text = ""
        elif fm.is_modified:
            text = "Modified"
        elif fm.last_saved is not None:
            text = f"Saved {format_relative_time(fm.last_saved)}"
        else:
            text = ""
        self._status_save.set_text(text)

    def _tick_save_time(self):
        self._update_save_label()
        return GLib.SOURCE_CONTINUE

    def _on_file_opened(self, tab_manager, path):
        root = self.file_explorer.root_path
        if root is None or not _is_within(path, root):
            self.file_explorer.set_root(os.path.dirname(path))

    def _on_sidebar_file_activated(self, widget, path):
        self.open_file(path)

    def _on_open_location(self, search_bar, path, line):
        tab = self.tab_manager.open_file(path)
        if tab is not None:
            tab.editor.goto_line(line)

    # ── View state ─────────────────────────────────────────────────────────

    def _set_view_mode(self, mode: str):
        self.activate_action("win.view-mode", GLib.Variant("s", mode))

    def _on_view_mode_changed(self, mode: str):
        if mode in MODES and self.split_view is not None:
            self.split_view.set_mode(mode)

    def _action_toggle_split(self, *_):
        current = self.lookup_action("view-mode").get_state().get_string()
        self._set_view_mode("editor" if current == "split" else "split")

    def _on_show_sidebar_changed(self, visible: bool):
        if visible:
            self._sidebar_box.set_visible(True)
            self._content_paned.set_position(self._sidebar_width)
        else:
            self._sidebar_width = max(self._content_paned.get_position(), SIDEBAR_DEFAULT_WIDTH)
            self._sidebar_box.set_visible(False)

    def _on_sidebar_paned_moved(self, paned, param):
        if self._sidebar_box.get_visible() and paned.get_position() > 40:
            self._sidebar_width = paned.get_position()

    def _on_show_minimap_changed(self, visible: bool):
        self._minimap.set_visible(visible)
        self._minimap_separator.set_visible(visible)

    # ── Action Callbacks ───────────────────────────────────────────────────

    def _action_new_file(self, *_):
        tab = self.tab_manager.active_tab
        if tab is not None and tab.file_manager.is_blank:
            tab.editor.grab_focus()
        else:
            self.tab_manager.new_tab()

    def _action_open_file(self, *_):
        fm = self.file_manager
        folder = self.file_explorer.root_path
        if fm is not None and fm.current_path:
            folder = os.path.dirname(fm.current_path)
        dialogs.choose_files_to_open(
            self, lambda paths: [self.open_file(p) for p in paths], folder=folder
        )

    def _action_fullscreen(self, *_):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _action_preferences(self, *_):
        from .preferences import PreferencesWindow
        PreferencesWindow(transient_for=self, settings=self.settings).present()

    def _action_show_shortcuts(self, *_):
        from .shortcuts import ShortcutsWindow
        ShortcutsWindow(transient_for=self).present()

    def _rebuild_recents_menu(self, *_):
        recents = self.recents_manager.get_recents(limit=MENU_LIMIT)
        menu = self._recents_menu
        menu.remove_all()
        files = Gio.Menu()
        for entry in recents:
            item = Gio.MenuItem.new(os.path.basename(entry["path"]), None)
            item.set_action_and_target_value("win.open-recent", GLib.Variant("s", entry["path"]))
            files.append_item(item)
        menu.append_section(None, files)
        if recents:
            clear = Gio.Menu()
            clear.append("Clear Recents", "win.clear-recents")
            menu.append_section(None, clear)

    def _show_goto_line_dialog(self):
        editor = self.editor
        if editor is None:
            return
        entry = Gtk.Entry(placeholder_text=f"1 – {editor.get_buffer().get_line_count()}")
        entry.set_input_purpose(Gtk.InputPurpose.NUMBER)

        def on_response(response):
            if response == "go":
                try:
                    editor.goto_line(int(entry.get_text().strip()) - 1)
                except ValueError:
                    pass

        dialog = dialogs.ask(
            self, "Go to Line", "",
            [("cancel", "Cancel", None), ("go", "Go", "suggested")],
            default="go", on_response=on_response, extra_child=entry,
        )
        entry.connect("activate", lambda _: dialog.respond("go"))
        entry.grab_focus()

    # ── Closing ────────────────────────────────────────────────────────────

    def _on_close_request(self, *_):
        if self._close_confirmed:
            return self._finish_close()
        dirty = self.tab_manager.modified_tabs()
        if not dirty:
            return self._finish_close()

        if len(dirty) == 1:
            self.tab_manager.select(dirty[0])
            dirty[0].file_manager.confirm_discard(self._close_if)
        else:
            names = "\n".join(f"• {t.file_manager.display_name}" for t in dirty)

            def on_response(rid):
                if rid == "save":
                    self.tab_manager.save_all(dirty, self._close_if)
                else:
                    self._close_if(rid == "discard")

            dialogs.ask(
                self,
                "Save Changes?",
                f"{len(dirty)} documents have unsaved changes:\n\n{names}",
                [("cancel", "Cancel", None), ("discard", "Discard All", "destructive"),
                 ("save", "Save All", "suggested")],
                default="save",
                on_response=on_response,
            )
        return True  # keep the window open until the user decides

    def _close_if(self, ok: bool):
        if ok:
            self._close_confirmed = True
            self.close()

    def _finish_close(self) -> bool:
        if self._save_tick:
            GLib.source_remove(self._save_tick)
            self._save_tick = 0
        self._word_count.cancel()
        return False  # let the window close

    # ── Public API ─────────────────────────────────────────────────────────

    def open_file(self, path: str):
        return self.tab_manager.open_file(path)
