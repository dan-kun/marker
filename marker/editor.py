"""GtkSourceView-based markdown editor."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")

from gi.repository import Gtk, GtkSource, GObject


class MarkdownEditor(Gtk.ScrolledWindow):
    """Editor widget wrapping GtkSourceView with MD support."""

    __gsignals__ = {
        "cursor-moved": (GObject.SignalFlags.RUN_LAST, None, (int, int)),
        "content-changed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._font_family = "Monospace"
        self._font_size = 13
        self._zoom_level = 1.0
        self._css_provider = Gtk.CssProvider()

        self._setup_buffer()
        self._setup_view()
        self.set_child(self._view)

    def _setup_buffer(self):
        lang_manager = GtkSource.LanguageManager.get_default()
        self._lang_md = lang_manager.get_language("markdown")
        self._lang_text = None

        self._buffer = GtkSource.Buffer()
        self._buffer.set_language(self._lang_md)
        self._buffer.set_highlight_syntax(True)
        self._buffer.set_highlight_matching_brackets(True)
        self._buffer.set_max_undo_levels(0)  # 0 = unlimited in GtkSource

        self._apply_scheme()
        self._buffer.connect("changed", self._on_buffer_changed)
        self._buffer.connect("notify::cursor-position", self._on_cursor_moved)

    def _apply_scheme(self):
        scheme_manager = GtkSource.StyleSchemeManager.get_default()
        scheme = scheme_manager.get_scheme("Adwaita")
        if not scheme:
            scheme = scheme_manager.get_scheme("classic")
        if scheme:
            self._buffer.set_style_scheme(scheme)

    def _setup_view(self):
        self._view = GtkSource.View.new_with_buffer(self._buffer)
        self._view.set_show_line_numbers(True)
        self._view.set_auto_indent(True)
        self._view.set_indent_on_tab(True)
        self._view.set_tab_width(4)
        self._view.set_insert_spaces_instead_of_tabs(True)
        self._view.set_highlight_current_line(True)
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._view.set_smart_home_end(GtkSource.SmartHomeEndType.BEFORE)
        self._view.set_monospace(True)
        self._view.set_vexpand(True)
        self._view.set_hexpand(True)
        self._view.set_left_margin(12)
        self._view.set_right_margin(12)
        self._view.set_top_margin(8)
        self._view.set_bottom_margin(8)
        self._update_font()

    def _update_font(self):
        size = int(self._font_size * self._zoom_level)
        css = f"textview {{ font-family: {self._font_family}; font-size: {size}pt; }}"
        self._css_provider.load_from_data(css.encode())
        self._view.get_style_context().add_provider(
            self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # ── Signal handlers ────────────────────────────────────────────────────

    def _on_buffer_changed(self, buf):
        text = self.get_text()
        self.emit("content-changed", text)

    def _on_cursor_moved(self, buf, param):
        mark = buf.get_insert()
        it = buf.get_iter_at_mark(mark)
        line = it.get_line() + 1
        col = it.get_line_offset() + 1
        self.emit("cursor-moved", line, col)

    # ── Public API ─────────────────────────────────────────────────────────

    def get_text(self) -> str:
        start = self._buffer.get_start_iter()
        end = self._buffer.get_end_iter()
        return self._buffer.get_text(start, end, True)

    def set_text(self, text: str):
        self._buffer.begin_irreversible_action()
        self._buffer.set_text(text)
        self._buffer.end_irreversible_action()

    def set_language(self, lang_id: str | None):
        if lang_id:
            lang_manager = GtkSource.LanguageManager.get_default()
            lang = lang_manager.get_language(lang_id)
            self._buffer.set_language(lang)
        else:
            self._buffer.set_language(None)

    def set_word_wrap(self, enabled: bool):
        if enabled:
            self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        else:
            self._view.set_wrap_mode(Gtk.WrapMode.NONE)

    def set_font(self, font_name: str, size: int):
        self._font_family = font_name
        self._font_size = size
        self._update_font()

    def set_tab_width(self, width: int):
        self._view.set_tab_width(width)

    def set_line_numbers(self, show: bool):
        self._view.set_show_line_numbers(show)

    def zoom_in(self):
        self._zoom_level = min(3.0, self._zoom_level + 0.1)
        self._update_font()

    def zoom_out(self):
        self._zoom_level = max(0.5, self._zoom_level - 0.1)
        self._update_font()

    def zoom_reset(self):
        self._zoom_level = 1.0
        self._update_font()

    def goto_line(self, line: int):
        it = self._buffer.get_iter_at_line(line)
        self._buffer.place_cursor(it)
        self._view.scroll_to_iter(it, 0.0, True, 0.0, 0.3)
        self._view.grab_focus()

    def undo(self):
        if self._buffer.can_undo():
            self._buffer.undo()

    def redo(self):
        if self._buffer.can_redo():
            self._buffer.redo()

    def get_buffer(self) -> GtkSource.Buffer:
        return self._buffer

    def get_view(self) -> GtkSource.View:
        return self._view

    def grab_focus(self):
        self._view.grab_focus()
