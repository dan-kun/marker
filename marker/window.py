"""Main application window for Marker."""

import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GLib
from .tab_view import TabManager
from .file_explorer import FileExplorer
from .search import SearchBar
from .recents import RecentFilesManager, MENU_LIMIT, format_relative_time
from .recents_section import RecentsSection
from .format_toolbar import FormatToolbar
from .menubar import build_menubar
from .minimap import Minimap


class MarkerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Marker")
        self.set_default_size(1200, 800)

        # Core components
        self.recents_manager = RecentFilesManager()
        self.tab_manager = TabManager(self, self.recents_manager)
        self.search_bar = SearchBar(self.editor)
        self.file_explorer = FileExplorer()

        self._minimap = Minimap()
        self._syncing_split = False
        self._tab_signal_ids = []
        self._last_save_time: float | None = None

        self._build_ui()
        self._setup_actions()
        self._setup_shortcuts()
        self._connect_signals()

        GLib.timeout_add_seconds(30, self._tick_save_time)

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
        # Root: vertical box
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        self._header = self._build_header()
        root_box.append(self._header)

        # Classic menubar
        self._menubar = build_menubar()
        self._menubar_recents_menu = self._menubar._recents_menu
        root_box.append(self._menubar)

        # Format toolbar
        self._format_toolbar = FormatToolbar()
        root_box.append(self._format_toolbar)
        root_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Content area: sidebar | main pane  (both resizable via Gtk.Paned)
        self._sidebar_width = 240  # last known width when visible

        self._content_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._content_paned.set_vexpand(True)
        self._content_paned.set_shrink_start_child(False)
        self._content_paned.set_shrink_end_child(False)
        self._content_paned.set_resize_start_child(False)
        self._content_paned.set_resize_end_child(True)
        self._content_paned.set_position(self._sidebar_width)

        # Track manual resizes so toggle restores the right width
        self._content_paned.connect("notify::position", self._on_sidebar_paned_moved)

        self._recents_section = RecentsSection(self.recents_manager)

        self.file_explorer.set_vexpand(True)

        self._sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._sidebar_box.set_size_request(220, -1)
        self._sidebar_box.append(self._recents_section)
        self._sidebar_box.append(self.file_explorer)

        self._content_paned.set_start_child(self._sidebar_box)

        # Editor area: search bar + tab manager
        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor_box.set_hexpand(True)
        editor_box.append(self.search_bar)
        editor_box.append(self.tab_manager)

        self._content_paned.set_end_child(editor_box)

        # Outer horizontal box: content paned + minimap
        outer_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer_hbox.set_vexpand(True)
        self._content_paned.set_vexpand(True)
        self._content_paned.set_hexpand(True)
        outer_hbox.append(self._content_paned)
        outer_hbox.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        outer_hbox.append(self._minimap)
        root_box.append(outer_hbox)

        # Status bar
        self._statusbar = self._build_statusbar()
        root_box.append(self._statusbar)

        self.set_content(root_box)

    def _build_header(self):
        header = Adw.HeaderBar()

        # Left side buttons
        left_box = Gtk.Box(spacing=4)

        btn_new = Gtk.Button(icon_name="document-new-symbolic", tooltip_text="New file (Ctrl+N)")
        btn_new.connect("clicked", lambda _: self.file_manager.new_file())
        left_box.append(btn_new)

        btn_open = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Open file (Ctrl+O)")
        btn_open.connect("clicked", lambda _: self.file_manager.open_file_dialog())
        left_box.append(btn_open)

        btn_save = Gtk.Button(icon_name="document-save-symbolic", tooltip_text="Save (Ctrl+S)")
        btn_save.connect("clicked", lambda _: self.file_manager.save_file())
        left_box.append(btn_save)

        header.pack_start(left_box)

        # Right side buttons
        right_box = Gtk.Box(spacing=4)

        btn_sidebar = Gtk.ToggleButton(
            icon_name="sidebar-show-symbolic",
            tooltip_text="Toggle sidebar (Ctrl+\\)",
            active=True,
        )
        btn_sidebar.connect("toggled", self._on_sidebar_toggled)
        self._btn_sidebar = btn_sidebar
        right_box.append(btn_sidebar)

        # View mode buttons
        view_box = Gtk.Box()
        view_box.add_css_class("linked")

        self._btn_editor_only = Gtk.ToggleButton(
            icon_name="text-editor-symbolic",
            tooltip_text="Editor only",
        )
        self._btn_split = Gtk.ToggleButton(
            icon_name="view-dual-symbolic",
            tooltip_text="Split view (Ctrl+E)",
            group=self._btn_editor_only,
        )
        self._btn_preview_only = Gtk.ToggleButton(
            icon_name="view-paged-symbolic",
            tooltip_text="Preview only (Ctrl+Shift+P)",
            group=self._btn_editor_only,
        )

        self._btn_split.set_active(True)
        self._btn_editor_only.connect(
            "toggled",
            lambda b: not getattr(self, "_syncing_split", False)
            and b.get_active()
            and self.split_view.set_mode("editor"),
        )
        self._btn_split.connect(
            "toggled",
            lambda b: not getattr(self, "_syncing_split", False)
            and b.get_active()
            and self.split_view.set_mode("split"),
        )
        self._btn_preview_only.connect(
            "toggled",
            lambda b: not getattr(self, "_syncing_split", False)
            and b.get_active()
            and self.split_view.set_mode("preview"),
        )

        view_box.append(self._btn_editor_only)
        view_box.append(self._btn_split)
        view_box.append(self._btn_preview_only)
        right_box.append(view_box)

        # Menu button
        menu_button = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            tooltip_text="Menu",
        )

        self._recents_menu = Gio.Menu()
        recents_submenu_section = Gio.Menu()
        recents_submenu_section.append_submenu("Open Recent", self._recents_menu)

        menu = Gio.Menu()
        menu.append_section(None, recents_submenu_section)

        app_section = Gio.Menu()
        app_section.append("Preferences", "win.preferences")
        app_section.append("Keyboard shortcuts", "win.show-shortcuts")
        app_section.append("About Marker", "app.about")
        menu.append_section(None, app_section)

        menu_button.set_menu_model(menu)
        right_box.append(menu_button)

        header.pack_end(right_box)

        # Title widget - shows filename
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

        self._status_pos = Gtk.Label(label="Ln 1, Col 1", xalign=0)
        self._status_pos.add_css_class("dim-label")
        bar.append(self._status_pos)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._status_words = Gtk.Label(label="0 words · < 1 min read", xalign=0)
        self._status_words.add_css_class("dim-label")
        bar.append(self._status_words)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._status_syntax = Gtk.Label(label="Plain Text", xalign=0)
        self._status_syntax.add_css_class("dim-label")
        bar.append(self._status_syntax)

        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        bar.append(spacer)

        self._status_encoding = Gtk.Label(label="UTF-8 · LF", xalign=1)
        self._status_encoding.add_css_class("dim-label")
        bar.append(self._status_encoding)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._status_save = Gtk.Label(label="", xalign=1)
        self._status_save.add_css_class("dim-label")
        bar.append(self._status_save)

        return bar

    # ── Actions ────────────────────────────────────────────────────────────

    def _setup_actions(self):
        actions = [
            ("new-file", self._action_new_file),
            ("open-file", self._action_open_file),
            ("save-file", self._action_save_file),
            ("save-file-as", self._action_save_file_as),
            ("close-file", self._action_close_file),
            ("new-tab", self._action_new_tab),
            ("next-tab", self._action_next_tab),
            ("prev-tab", self._action_prev_tab),
            ("find", self._action_find),
            ("find-replace", self._action_find_replace),
            ("find-in-dir", self._action_find_in_dir),
            ("toggle-split", self._action_toggle_split),
            ("preview-only", self._action_preview_only),
            ("toggle-sidebar", self._action_toggle_sidebar),
            ("fullscreen", self._action_fullscreen),
            ("zoom-in", self._action_zoom_in),
            ("zoom-out", self._action_zoom_out),
            ("zoom-reset", self._action_zoom_reset),
            ("goto-line", self._action_goto_line),
            ("preferences", self._action_preferences),
            ("show-shortcuts", self._action_show_shortcuts),
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        open_recent = Gio.SimpleAction.new("open-recent", GLib.VariantType.new("s"))
        open_recent.connect("activate", self._action_open_recent)
        self.add_action(open_recent)

        clear_recents = Gio.SimpleAction.new("clear-recents", None)
        clear_recents.connect("activate", lambda *_: self.recents_manager.clear())
        self.add_action(clear_recents)

        goto_tab = Gio.SimpleAction.new("goto-tab", GLib.VariantType.new("i"))
        goto_tab.connect("activate", lambda a, p: self.tab_manager.goto_tab(p.get_int32() - 1))
        self.add_action(goto_tab)

        toggle_minimap_action = Gio.SimpleAction.new("toggle-minimap", None)
        toggle_minimap_action.connect(
            "activate",
            lambda *_: self._minimap.set_visible(not self._minimap.get_visible()),
        )
        self.add_action(toggle_minimap_action)

        editor_only_action = Gio.SimpleAction.new("editor-only", None)
        editor_only_action.connect(
            "activate",
            lambda *_: (
                self.split_view.set_mode("editor"),
                self._btn_editor_only.set_active(True),
            ),
        )
        self.add_action(editor_only_action)

        format_actions = [
            ("format-bold",          lambda *_: self.editor.insert_bold()),
            ("format-italic",        lambda *_: self.editor.insert_italic()),
            ("format-code",          lambda *_: self.editor.insert_code()),
            ("format-link",          lambda *_: self.editor.insert_link()),
            ("format-bullet-list",   lambda *_: self.editor.insert_bullet_list()),
            ("format-numbered-list", lambda *_: self.editor.insert_numbered_list()),
        ]
        for name, callback in format_actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        heading_action = Gio.SimpleAction.new("format-heading", GLib.VariantType.new("i"))
        heading_action.connect("activate", lambda a, p: self.editor.insert_heading(p.get_int32()))
        self.add_action(heading_action)

    def _setup_shortcuts(self):
        app = self.get_application()
        accel_map = {
            "win.new-file": ["<Ctrl>n"],
            "win.open-file": ["<Ctrl>o"],
            "win.save-file": ["<Ctrl>s"],
            "win.save-file-as": ["<Ctrl><Shift>s"],
            "win.close-file": ["<Ctrl>w"],
            "win.new-tab": ["<Ctrl>t"],
            "win.next-tab": ["<Ctrl>Tab"],
            "win.prev-tab": ["<Ctrl><Shift>Tab"],
            "win.find": ["<Ctrl>f"],
            "win.find-replace": ["<Ctrl>h"],
            "win.find-in-dir": ["<Ctrl><Shift>f"],
            "win.toggle-split": ["<Ctrl>e"],
            "win.preview-only": ["<Ctrl><Shift>p"],
            "win.toggle-sidebar": ["<Ctrl>backslash"],
            "win.fullscreen": ["F11"],
            "win.zoom-in": ["<Ctrl>plus", "<Ctrl>equal"],
            "win.zoom-out": ["<Ctrl>minus"],
            "win.zoom-reset": ["<Ctrl>0"],
            "win.goto-line": ["<Ctrl>g"],
            "win.preferences": ["<Ctrl>comma"],
            "win.format-bold": ["<Ctrl>b"],
            "win.format-italic": ["<Ctrl>i"],
            "win.format-code": ["<Ctrl>grave"],
            "win.format-link": ["<Ctrl>l"],
            "win.toggle-minimap": ["<Ctrl>m"],
        }
        for action, accels in accel_map.items():
            app.set_accels_for_action(action, accels)

        # goto-tab(1) … goto-tab(9) with Ctrl+1 … Ctrl+9
        for i in range(1, 10):
            app.set_accels_for_action(
                f"win.goto-tab({i})", [f"<Ctrl>{i}"]
            )

    # ── Signals ────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self._tab_signal_ids = []
        self.tab_manager.connect("active-tab-changed", self._on_active_tab_changed)
        self.file_explorer.connect("file-activated", self._on_explorer_file_activated)
        self._recents_section.connect("file-activated", self._on_explorer_file_activated)
        self.recents_manager.connect("changed", self._rebuild_recents_menu)
        self._rebuild_recents_menu()
        self._connect_active_tab()

    def _on_active_tab_changed(self, *_):
        self._connect_active_tab()

    def _connect_active_tab(self):
        # Disconnect previous tab's signals
        for obj, hid in self._tab_signal_ids:
            obj.disconnect(hid)
        self._tab_signal_ids = []

        ed = self.editor
        fm = self.file_manager
        if ed is None:
            return

        self._tab_signal_ids = [
            (ed, ed.connect("cursor-moved", self._on_cursor_moved)),
            (ed, ed.connect("content-changed", self._on_content_changed)),
            (fm, fm.connect("file-changed", self._on_file_changed)),
        ]

        # Sync UI from new active tab's state
        self._sync_split_buttons()
        self.search_bar.set_editor(ed)
        self._minimap.set_editor(ed)

        # Trigger immediate status bar update
        buf = ed.get_buffer()
        it = buf.get_iter_at_mark(buf.get_insert())
        self._on_cursor_moved(ed, it.get_line() + 1, it.get_line_offset() + 1)
        self._on_content_changed(ed, ed.get_text())
        self._on_file_changed(fm, fm.current_path or "", fm.is_modified)

    def _sync_split_buttons(self):
        sv = self.split_view
        if sv is None:
            return
        mode = sv.get_mode()
        self._syncing_split = True
        self._btn_editor_only.set_active(mode == "editor")
        self._btn_split.set_active(mode == "split")
        self._btn_preview_only.set_active(mode == "preview")
        self._syncing_split = False

    def _on_cursor_moved(self, editor, line, col):
        self._status_pos.set_text(f"Ln {line}, Col {col}")

    def _on_content_changed(self, editor, text):
        words = len(text.split()) if text.strip() else 0
        if words >= 110:
            mins = max(1, round(words / 220))
            time_str = f"· {mins} min read"
        else:
            time_str = "· < 1 min read"
        self._status_words.set_text(f"{words} words {time_str}")

    def _on_file_changed(self, fm, path, is_modified):
        if path:
            name = os.path.basename(path)
            title = f"{'• ' if is_modified else ''}{name}"
            self._title_widget.set_title(title)
            self._title_widget.set_subtitle(path)
        else:
            self._title_widget.set_title("Marker")
            self._title_widget.set_subtitle("")

        # Syntax label
        if path:
            ext = os.path.splitext(path)[1].lower()
            self._status_syntax.set_text(
                "Markdown" if ext in {".md", ".markdown", ".mkd", ".mdown"} else "Plain Text"
            )
        else:
            self._status_syntax.set_text("Plain Text")

        # Save status
        import time as _time
        if is_modified:
            self._status_save.set_text("Modified")
            self._last_save_time = None
        elif path:
            self._last_save_time = _time.time()
            self._status_save.set_text("Saved just now")
        else:
            self._status_save.set_text("")
            self._last_save_time = None

    def _tick_save_time(self):
        if self._last_save_time is not None:
            self._status_save.set_text(f"Saved {format_relative_time(self._last_save_time)}")
        return True  # keep ticking

    def _on_explorer_file_activated(self, explorer, path):
        self.file_manager.open_file(path)

    def _on_sidebar_paned_moved(self, paned, param):
        if self._sidebar_box.get_visible():
            pos = paned.get_position()
            if pos > 40:
                self._sidebar_width = pos

    def _on_sidebar_toggled(self, btn):
        if btn.get_active():
            self._sidebar_box.set_visible(True)
            self._content_paned.set_position(self._sidebar_width)
        else:
            self._sidebar_width = max(self._content_paned.get_position(), 240)
            self._sidebar_box.set_visible(False)

    # ── Action Callbacks ───────────────────────────────────────────────────

    def _action_new_file(self, *_):
        self.file_manager.new_file()

    def _action_open_file(self, *_):
        self.file_manager.open_file_dialog()

    def _action_save_file(self, *_):
        self.file_manager.save_file()

    def _action_save_file_as(self, *_):
        self.file_manager.save_file_as()

    def _action_close_file(self, *_):
        self.tab_manager.close_active_tab()

    def _action_new_tab(self, *_):
        self.tab_manager.new_tab()

    def _action_next_tab(self, *_):
        self.tab_manager.next_tab()

    def _action_prev_tab(self, *_):
        self.tab_manager.prev_tab()

    def _action_find(self, *_):
        self.search_bar.show_search()

    def _action_find_replace(self, *_):
        self.search_bar.show_replace()

    def _action_find_in_dir(self, *_):
        self.search_bar.show_dir_search()

    def _action_toggle_split(self, *_):
        current = self.split_view.get_mode()
        if current == "split":
            self.split_view.set_mode("editor")
            self._btn_editor_only.set_active(True)
        else:
            self.split_view.set_mode("split")
            self._btn_split.set_active(True)

    def _action_preview_only(self, *_):
        self.split_view.set_mode("preview")
        self._btn_preview_only.set_active(True)

    def _action_toggle_sidebar(self, *_):
        current = self._btn_sidebar.get_active()
        self._btn_sidebar.set_active(not current)
        # _on_sidebar_toggled fires via the toggled signal

    def _action_fullscreen(self, *_):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _action_zoom_in(self, *_):
        self.editor.zoom_in()
        self.preview.zoom_in()

    def _action_zoom_out(self, *_):
        self.editor.zoom_out()
        self.preview.zoom_out()

    def _action_zoom_reset(self, *_):
        self.editor.zoom_reset()
        self.preview.zoom_reset()

    def _action_goto_line(self, *_):
        self._show_goto_line_dialog()

    def _action_preferences(self, *_):
        from .preferences import PreferencesWindow
        prefs = PreferencesWindow(transient_for=self, editor=self.editor)
        prefs.present()

    def _action_show_shortcuts(self, *_):
        from .shortcuts import ShortcutsWindow
        shortcuts = ShortcutsWindow(transient_for=self)
        shortcuts.present()

    def _action_open_recent(self, action, param):
        path = param.get_string()
        self.file_manager.open_file(path)

    def _rebuild_recents_menu(self, *_):
        recents = self.recents_manager.get_recents(limit=MENU_LIMIT)

        for menu in (self._recents_menu, self._menubar_recents_menu):
            menu.remove_all()
            for entry in recents:
                item = Gio.MenuItem.new(os.path.basename(entry["path"]), None)
                item.set_action_and_target_value(
                    "win.open-recent", GLib.Variant("s", entry["path"])
                )
                menu.append_item(item)
            if recents:
                menu.append("Clear Recents", "win.clear-recents")

    def _show_goto_line_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Go to Line",
        )
        entry = Gtk.Entry(placeholder_text="Line number")
        entry.set_input_purpose(Gtk.InputPurpose.NUMBER)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("go", "Go")
        dialog.set_default_response("go")
        dialog.set_response_appearance("go", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "go":
                try:
                    line = int(entry.get_text()) - 1
                    self.editor.goto_line(max(0, line))
                except ValueError:
                    pass

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("go"))
        dialog.present()

    # ── Public API ─────────────────────────────────────────────────────────

    def open_file(self, path: str):
        self.file_manager.open_file(path)
