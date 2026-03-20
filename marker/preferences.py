"""Preferences window for Marker (compatible with libadwaita 1.1)."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw

_DEFAULTS = {
    "font-family": "Monospace",
    "font-size": 13,
    "tab-width": 4,
    "word-wrap": True,
    "line-numbers": True,
    "auto-save": False,
    "auto-save-delay": 30,
}


class Settings:
    _instance = None
    _data: dict = {}

    @classmethod
    def get(cls) -> "Settings":
        if cls._instance is None:
            cls._instance = cls()
            cls._data = dict(_DEFAULTS)
        return cls._instance

    def __getitem__(self, key):
        return self._data.get(key, _DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self._data[key] = value


def _spin(value, lo, hi, step=1) -> Gtk.SpinButton:
    adj = Gtk.Adjustment(value=value, lower=lo, upper=hi, step_increment=step)
    btn = Gtk.SpinButton(adjustment=adj, digits=0)
    btn.set_valign(Gtk.Align.CENTER)
    btn.set_width_chars(5)
    return btn


def _switch(active: bool) -> Gtk.Switch:
    sw = Gtk.Switch(active=active)
    sw.set_valign(Gtk.Align.CENTER)
    return sw


def _action_row(title, subtitle, widget) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    row.add_suffix(widget)
    row.set_activatable_widget(widget)
    return row


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, editor, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Preferences")
        self.set_default_size(480, 480)
        self.set_search_enabled(False)
        self._editor = editor
        self._settings = Settings.get()
        self._build_ui()

    def _build_ui(self):
        page = Adw.PreferencesPage(
            title="Editor",
            icon_name="accessories-text-editor-symbolic",
        )

        # ── Font ──────────────────────────────────────────────────────────
        font_group = Adw.PreferencesGroup(title="Font")

        self._font_entry = Gtk.Entry(text=self._settings["font-family"])
        self._font_entry.set_valign(Gtk.Align.CENTER)
        self._font_entry.set_width_chars(16)
        font_group.add(_action_row("Font Family", "Editor font name", self._font_entry))

        self._font_size = _spin(self._settings["font-size"], 8, 32)
        font_group.add(_action_row("Font Size", "Size in points", self._font_size))

        page.add(font_group)

        # ── Editing ───────────────────────────────────────────────────────
        edit_group = Adw.PreferencesGroup(title="Editing")

        self._tab_width = _spin(self._settings["tab-width"], 1, 8)
        edit_group.add(_action_row("Tab Width", "Spaces per tab", self._tab_width))

        self._word_wrap = _switch(self._settings["word-wrap"])
        edit_group.add(_action_row("Word Wrap", "Wrap long lines at word boundaries", self._word_wrap))

        self._line_numbers = _switch(self._settings["line-numbers"])
        edit_group.add(_action_row("Line Numbers", "Show line numbers in the gutter", self._line_numbers))

        page.add(edit_group)

        # ── Auto-save ─────────────────────────────────────────────────────
        save_group = Adw.PreferencesGroup(title="Auto-save")

        self._auto_save = _switch(self._settings["auto-save"])
        save_group.add(_action_row("Auto-save", "Automatically save changes", self._auto_save))

        self._auto_save_delay = _spin(self._settings["auto-save-delay"], 5, 300, step=5)
        save_group.add(_action_row("Delay (seconds)", "Time between auto-saves", self._auto_save_delay))

        page.add(save_group)

        self.add(page)

        # Apply button in the header
        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply)
        self.add_action_widget(apply_btn) if hasattr(self, "add_action_widget") else None

        # Fallback: connect to close
        self.connect("close-request", self._on_close)

    def _on_apply(self, _btn):
        self._save_settings()
        self.close()

    def _on_close(self, _win):
        self._save_settings()
        return False  # allow close

    def _save_settings(self):
        s = self._settings
        s["font-family"] = self._font_entry.get_text().strip() or "Monospace"
        s["font-size"] = int(self._font_size.get_value())
        s["tab-width"] = int(self._tab_width.get_value())
        s["word-wrap"] = self._word_wrap.get_active()
        s["line-numbers"] = self._line_numbers.get_active()
        s["auto-save"] = self._auto_save.get_active()
        s["auto-save-delay"] = int(self._auto_save_delay.get_value())
        self._apply_to_editor()

    def _apply_to_editor(self):
        s = self._settings
        self._editor.set_font(s["font-family"], s["font-size"])
        self._editor.set_tab_width(s["tab-width"])
        self._editor.set_word_wrap(s["word-wrap"])
        self._editor.set_line_numbers(s["line-numbers"])
