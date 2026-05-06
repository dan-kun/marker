"""Main application window for Marker."""

import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GLib
from .editor import MarkdownEditor
from .preview import MarkdownPreview
from .split_view import SplitView
from .file_manager import FileManager
from .file_explorer import FileExplorer
from .search import SearchBar
from .recents import RecentFilesManager, MENU_LIMIT
from .recents_section import RecentsSection


class MarkerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Marker")
        self.set_default_size(1200, 800)

        # Core components
        self.editor = MarkdownEditor()
        self.preview = MarkdownPreview()
        self.recents_manager = RecentFilesManager()
        self.file_manager = FileManager(self, self.recents_manager)
        self.search_bar = SearchBar(self.editor)
        self.file_explorer = FileExplorer()

        self._build_ui()
        self._setup_actions()
        self._setup_shortcuts()
        self._connect_signals()

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self):
        # Root: vertical box
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        self._header = self._build_header()
        root_box.append(self._header)

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

        # Split view (editor + preview)
        self.split_view = SplitView(self.editor, self.preview)
        self.split_view.set_hexpand(True)

        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor_box.set_hexpand(True)
        editor_box.append(self.search_bar)
        editor_box.append(self.split_view)

        self._content_paned.set_end_child(editor_box)
        root_box.append(self._content_paned)

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
        self._btn_editor_only.connect("toggled", lambda b: b.get_active() and self.split_view.set_mode("editor"))
        self._btn_split.connect("toggled", lambda b: b.get_active() and self.split_view.set_mode("split"))
        self._btn_preview_only.connect("toggled", lambda b: b.get_active() and self.split_view.set_mode("preview"))

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

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        bar.append(sep)

        self._status_words = Gtk.Label(label="0 words", xalign=0)
        self._status_words.add_css_class("dim-label")
        bar.append(self._status_words)

        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        bar.append(spacer)

        self._status_encoding = Gtk.Label(label="UTF-8", xalign=1)
        self._status_encoding.add_css_class("dim-label")
        bar.append(self._status_encoding)

        return bar

    # ── Actions ────────────────────────────────────────────────────────────

    def _setup_actions(self):
        actions = [
            ("new-file", self._action_new_file),
            ("open-file", self._action_open_file),
            ("save-file", self._action_save_file),
            ("save-file-as", self._action_save_file_as),
            ("close-file", self._action_close_file),
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

    def _setup_shortcuts(self):
        app = self.get_application()
        accel_map = {
            "win.new-file": ["<Ctrl>n"],
            "win.open-file": ["<Ctrl>o"],
            "win.save-file": ["<Ctrl>s"],
            "win.save-file-as": ["<Ctrl><Shift>s"],
            "win.close-file": ["<Ctrl>w"],
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
        }
        for action, accels in accel_map.items():
            app.set_accels_for_action(action, accels)

    # ── Signals ────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.editor.connect("cursor-moved", self._on_cursor_moved)
        self.editor.connect("content-changed", self._on_content_changed)
        self.file_manager.connect("file-changed", self._on_file_changed)
        self.file_explorer.connect("file-activated", self._on_explorer_file_activated)
        self._recents_section.connect("file-activated", self._on_explorer_file_activated)
        self.recents_manager.connect("changed", self._rebuild_recents_menu)
        self._rebuild_recents_menu()

    def _on_cursor_moved(self, editor, line, col):
        self._status_pos.set_text(f"Ln {line}, Col {col}")

    def _on_content_changed(self, editor, text):
        words = len(text.split()) if text.strip() else 0
        self._status_words.set_text(f"{words} words")

    def _on_file_changed(self, fm, path, is_modified):
        if path:
            name = os.path.basename(path)
            title = f"{'• ' if is_modified else ''}{name}"
            self._title_widget.set_title(title)
            self._title_widget.set_subtitle(path)
        else:
            self._title_widget.set_title("Marker")
            self._title_widget.set_subtitle("")

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
        self.file_manager.close_file()

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
        self._recents_menu.remove_all()
        recents = self.recents_manager.get_recents(limit=MENU_LIMIT)
        for entry in recents:
            item = Gio.MenuItem.new(os.path.basename(entry["path"]), None)
            item.set_action_and_target_value(
                "win.open-recent", GLib.Variant("s", entry["path"])
            )
            self._recents_menu.append_item(item)
        if recents:
            self._recents_menu.append("Clear Recents", "win.clear-recents")

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
