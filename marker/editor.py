"""GtkSourceView-based markdown editor."""

import itertools
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gdk, GObject, Gtk, GtkSource

from . import mdedit
from .shortcuts import editor_accels

_editor_ids = itertools.count(1)


class MarkdownEditor(Gtk.ScrolledWindow):
    """Editor widget wrapping GtkSourceView with MD support."""

    __gsignals__ = {
        "cursor-moved": (GObject.SignalFlags.RUN_LAST, None, (int, int)),
        # No payload: listeners call get_text() only when they need it.
        "content-changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._font_family = "Monospace"
        self._font_size = 13
        self._zoom_level = 1.0
        self._css_provider = Gtk.CssProvider()
        self._css_name = f"marker-editor-{next(_editor_ids)}"
        self._display = None

        self._setup_buffer()
        self._setup_view()
        self.set_child(self._view)

    def _setup_buffer(self):
        lang_manager = GtkSource.LanguageManager.get_default()
        self._lang_md = lang_manager.get_language("markdown")

        self._buffer = GtkSource.Buffer()
        self._buffer.set_language(self._lang_md)
        self._buffer.set_highlight_syntax(True)
        self._buffer.set_highlight_matching_brackets(True)
        self._buffer.set_max_undo_levels(0)  # 0 = unlimited in GtkSource

        self._apply_scheme()
        # StyleManager is a process-wide singleton: disconnected in dispose()
        self._style_handler = Adw.StyleManager.get_default().connect(
            "notify::dark", self._apply_scheme
        )
        self._buffer_handlers = [
            self._buffer.connect("changed", self._on_buffer_changed),
            self._buffer.connect("notify::cursor-position", self._on_cursor_moved),
        ]

    def _apply_scheme(self, *_):
        """Use the light or dark Adwaita scheme to match the app's theme."""
        dark = Adw.StyleManager.get_default().get_dark()
        scheme_manager = GtkSource.StyleSchemeManager.get_default()
        candidates = ("Adwaita-dark", "classic-dark") if dark else ("Adwaita", "classic")
        for scheme_id in candidates:
            scheme = scheme_manager.get_scheme(scheme_id)
            if scheme:
                self._buffer.set_style_scheme(scheme)
                return

    def _setup_view(self):
        self._view = GtkSource.View.new_with_buffer(self._buffer)
        self._view.set_name(self._css_name)
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

        # List editing: Enter continues a list, Tab / Shift+Tab nest items.
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key_pressed)
        self._view.add_controller(keys)
        self._key_controller = keys

        # Formatting shortcuts belong to the editor, not the whole window:
        # Ctrl+B while typing in the search box must not edit the document.
        shortcuts = Gtk.ShortcutController()
        for accel, action in editor_accels():
            shortcuts.add_shortcut(Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string(accel), Gtk.NamedAction.new(action)
            ))
        self._view.add_controller(shortcuts)

        # One provider per editor, registered once and scoped by widget name.
        self._display = Gdk.Display.get_default()
        if self._display is not None:
            Gtk.StyleContext.add_provider_for_display(
                self._display, self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        self._update_font()

    def _update_font(self):
        size = max(4, round(self._font_size * self._zoom_level))
        family = re.sub(r'[\\"{};]', "", self._font_family).strip() or "Monospace"
        css = f'textview#{self._css_name} {{ font-family: "{family}", monospace; font-size: {size}pt; }}'
        if hasattr(self._css_provider, "load_from_string"):  # GTK ≥ 4.12
            self._css_provider.load_from_string(css)
        else:
            self._css_provider.load_from_data(css.encode())

    def dispose(self):
        """Release resources that outlive the widget (called when its tab closes)."""
        if self._display is not None:
            Gtk.StyleContext.remove_provider_for_display(self._display, self._css_provider)
            self._display = None
        if self._style_handler:
            Adw.StyleManager.get_default().disconnect(self._style_handler)
            self._style_handler = 0
        # These closures reference self; left connected they keep the
        # editor and its whole text buffer alive after the tab closes.
        for handler in self._buffer_handlers:
            self._buffer.disconnect(handler)
        self._buffer_handlers = []
        if self._key_controller is not None:
            self._view.remove_controller(self._key_controller)
            self._key_controller = None

    # ── Signal handlers ────────────────────────────────────────────────────

    def _on_buffer_changed(self, buf):
        self.emit("content-changed")

    def _on_cursor_moved(self, buf, param):
        line, col = self.get_cursor_position()
        self.emit("cursor-moved", line, col)

    # ── Public API ─────────────────────────────────────────────────────────

    def get_text(self) -> str:
        start = self._buffer.get_start_iter()
        end = self._buffer.get_end_iter()
        return self._buffer.get_text(start, end, True)

    def set_text(self, text: str):
        """Replace the whole document. Not undoable; cursor goes to the start."""
        self._buffer.begin_irreversible_action()
        self._buffer.set_text(text)
        self._buffer.end_irreversible_action()
        self._buffer.place_cursor(self._buffer.get_start_iter())

    def is_empty(self) -> bool:
        return self._buffer.get_char_count() == 0

    def get_cursor_position(self) -> tuple[int, int]:
        """1-based (line, column) of the insertion cursor."""
        it = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        return it.get_line() + 1, it.get_line_offset() + 1

    def set_language(self, lang_id: str | None):
        if lang_id:
            lang_manager = GtkSource.LanguageManager.get_default()
            self._buffer.set_language(lang_manager.get_language(lang_id))
        else:
            self._buffer.set_language(None)

    def apply_settings(self, settings):
        self._font_family = settings["font-family"]
        self._font_size = settings["font-size"]
        self._update_font()
        self._view.set_tab_width(settings["tab-width"])
        self._view.set_wrap_mode(
            Gtk.WrapMode.WORD_CHAR if settings["word-wrap"] else Gtk.WrapMode.NONE
        )
        self._view.set_show_line_numbers(settings["line-numbers"])

    @property
    def zoom_level(self) -> float:
        return self._zoom_level

    def set_zoom(self, level: float):
        level = max(0.5, min(3.0, level))
        if level != self._zoom_level:
            self._zoom_level = level
            self._update_font()

    def get_top_line(self) -> float:
        """The 0-based line at the top of the visible area, with a fraction
        for how far that line (which may wrap over many rows) is scrolled."""
        top = self._view.get_visible_rect().y
        it, _ = self._view.get_line_at_y(top)
        line_y, line_height = self._view.get_line_yrange(it)
        inside = (top - line_y) / line_height if line_height > 0 else 0.0
        return it.get_line() + min(1.0, max(0.0, inside))

    def set_cursor_position(self, line: int, column: int):
        """Place the cursor at a 1-based (line, column), clamped to the text,
        and keep it in view. Unlike goto_line() this does not take the focus."""
        buf = self._buffer
        line = max(0, min(line - 1, buf.get_line_count() - 1))
        it = self._iter_at_line(line)
        it.forward_chars(max(0, min(column - 1, it.get_chars_in_line() - 1)))
        buf.place_cursor(it)
        self._view.scroll_mark_onscreen(buf.get_insert())

    def goto_line(self, line: int):
        """Move the cursor to a 0-based line and scroll it into view."""
        line = max(0, min(line, self._buffer.get_line_count() - 1))
        it = self._iter_at_line(line)
        self._buffer.place_cursor(it)
        self._view.scroll_to_iter(it, 0.0, True, 0.0, 0.3)
        self._view.grab_focus()

    def _iter_at_line(self, line: int):
        result = self._buffer.get_iter_at_line(line)
        # PyGObject ≥ 3.44 returns (bool, GtkTextIter); older returns just GtkTextIter
        return result[1] if isinstance(result, tuple) else result

    def undo(self):
        if self._buffer.get_can_undo():
            self._buffer.undo()

    def redo(self):
        if self._buffer.get_can_redo():
            self._buffer.redo()

    def get_buffer(self) -> GtkSource.Buffer:
        return self._buffer

    def get_view(self) -> GtkSource.View:
        return self._view

    def grab_focus(self) -> bool:
        return self._view.grab_focus()

    def get_selection(self) -> tuple[Gtk.TextIter, Gtk.TextIter] | None:
        """(start, end) of the selected text, or None when nothing is selected."""
        bounds = self._buffer.get_selection_bounds()
        return (bounds[0], bounds[1]) if bounds else None

    # ── Markdown insert helpers ────────────────────────────────────────────
    # Each helper toggles: applying it to text that already has the
    # formatting removes it. The rules live in mdedit.py.

    def insert_bold(self):
        self._toggle_wrap("**", "**")

    def insert_italic(self):
        self._toggle_wrap("*", "*")

    def insert_code(self):
        selection = self.get_selection()
        if selection and "\n" in self._buffer.get_text(*selection, True):
            self._toggle_wrap("```\n", "\n```")
            return
        self._toggle_wrap("`", "`")

    def insert_heading(self, level: int):
        prefix = "#" * level + " "
        buf = self._buffer
        it = buf.get_iter_at_mark(buf.get_insert())
        line_num = it.get_line()
        line_start = self._iter_at_line(line_num)
        line_end = line_start.copy()
        if not line_end.ends_line():
            line_end.forward_to_line_end()
        line_text = buf.get_text(line_start, line_end, True)

        # Strip any existing heading prefix
        stripped = line_text
        while stripped.startswith("#"):
            stripped = stripped[1:]
        if stripped.startswith(" "):
            stripped = stripped[1:]

        new_text = stripped if line_text == f"{prefix}{stripped}" else f"{prefix}{stripped}"

        buf.begin_user_action()
        buf.delete(line_start, line_end)
        if new_text:
            buf.insert(line_start, new_text)
        buf.end_user_action()

    def insert_link(self):
        buf = self._buffer
        selection = self.get_selection()
        buf.begin_user_action()
        if selection:
            start, end = selection
            text = buf.get_text(start, end, True)
            buf.delete(start, end)
            it = buf.get_iter_at_mark(buf.get_insert())
            buf.insert(it, f"[{text}](url)")
            # Select "url" so the user can type the URL immediately
            it = buf.get_iter_at_mark(buf.get_insert())
            url_end = it.copy()
            url_end.backward_chars(1)   # before ')'
            it.backward_chars(4)        # before 'url)'
            buf.select_range(it, url_end)
        else:
            it = buf.get_iter_at_mark(buf.get_insert())
            buf.insert(it, "[text](url)")
            # Select "text" so the user can type the link text immediately
            it = buf.get_iter_at_mark(buf.get_insert())
            text_end = it.copy()
            text_end.backward_chars(6)   # before ](url)
            text_start = it.copy()
            text_start.backward_chars(10)  # before 'text'
            buf.select_range(text_start, text_end)
        buf.end_user_action()

    def insert_bullet_list(self):
        self._rewrite_lines(mdedit.toggle_bullets)

    def insert_numbered_list(self):
        self._rewrite_lines(mdedit.toggle_numbering)

    def _toggle_wrap(self, prefix: str, suffix: str):
        buf = self._buffer
        selection = self.get_selection()
        if selection:
            start, end = selection
        else:
            start = buf.get_iter_at_mark(buf.get_insert())
            end = start.copy()

        # mdedit only needs the selection plus the few characters around it
        context_start, context_end = start.copy(), end.copy()
        context_start.backward_chars(len(prefix) + 2)
        context_end.forward_chars(len(suffix) + 2)
        base = context_start.get_offset()
        edit = mdedit.toggle_wrap(
            buf.get_text(context_start, context_end, True),
            start.get_offset() - base, end.get_offset() - base, prefix, suffix,
        )

        buf.begin_user_action()
        edit_start = buf.get_iter_at_offset(base + edit.start)
        buf.delete(edit_start, buf.get_iter_at_offset(base + edit.end))
        buf.insert(edit_start, edit.text)
        buf.select_range(
            buf.get_iter_at_offset(base + edit.select_start),
            buf.get_iter_at_offset(base + edit.select_end),
        )
        buf.end_user_action()

    def _selected_line_range(self) -> tuple[int, int]:
        """First and last line touched by the selection (or the cursor's line)."""
        buf = self._buffer
        selection = self.get_selection()
        if not selection:
            line = buf.get_iter_at_mark(buf.get_insert()).get_line()
            return line, line
        start, end = selection
        first, last = start.get_line(), end.get_line()
        if end.get_line_offset() == 0 and last > first:
            last -= 1  # a selection ending at a line's start does not include that line
        return first, last

    def _rewrite_lines(self, transform):
        """Replace the selected lines with transform(lines)."""
        buf = self._buffer
        first, last = self._selected_line_range()
        start = self._iter_at_line(first)
        end = self._iter_at_line(last)
        if not end.ends_line():
            end.forward_to_line_end()
        lines = buf.get_text(start, end, True).split("\n")

        buf.begin_user_action()
        buf.delete(start, end)
        buf.insert(start, "\n".join(transform(lines)))
        buf.end_user_action()

    # ── Keys ───────────────────────────────────────────────────────────────

    def _current_line(self) -> tuple[Gtk.TextIter, str, int]:
        """(iter at line start, line text, cursor column) for the cursor's line."""
        buf = self._buffer
        cursor = buf.get_iter_at_mark(buf.get_insert())
        line_start = self._iter_at_line(cursor.get_line())
        line_end = line_start.copy()
        if not line_end.ends_line():
            line_end.forward_to_line_end()
        return line_start, buf.get_text(line_start, line_end, True), cursor.get_line_offset()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        buf = self._buffer
        if buf.get_has_selection() or not self._view.get_editable():
            return False
        modifiers = state & (
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK
        )
        if modifiers:
            return False
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not shift:
            return self._continue_list()
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            return self._indent_list_item(unindent=shift or keyval == Gdk.KEY_ISO_Left_Tab)
        return False

    def _continue_list(self) -> bool:
        """Enter in a list item starts the next one; in an empty item it ends the list."""
        buf = self._buffer
        line_start, line, column = self._current_line()
        action = mdedit.list_enter(line, column)
        if action is None:
            return False
        kind, text = action
        buf.begin_user_action()
        if kind == "continue":
            buf.insert_at_cursor(text)
        else:
            marker_end = line_start.copy()
            marker_end.forward_chars(len(text))
            buf.delete(line_start, marker_end)
        buf.end_user_action()
        self._view.scroll_mark_onscreen(buf.get_insert())
        return True

    def _indent_list_item(self, unindent: bool) -> bool:
        """Tab / Shift+Tab on a list item changes its nesting level."""
        line_start, line, _ = self._current_line()
        if mdedit.list_item_end(line) is None:
            return False
        line_end = line_start.copy()
        if not line_end.ends_line():
            line_end.forward_to_line_end()
        if unindent:
            self._view.unindent_lines(line_start, line_end)
        else:
            self._view.indent_lines(line_start, line_end)
        return True
