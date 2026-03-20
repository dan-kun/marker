"""Preferences window for Marker."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib

# GSettings schema ID (or simple dict-based settings for now)
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
    """Simple in-memory settings store (no GSettings schema needed)."""
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


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, editor, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Preferences")
        self.set_default_size(480, 520)
        self._editor = editor
        self._settings = Settings.get()

        self._build_ui()

    def _build_ui(self):
        # ── Editor page ────────────────────────────────────────────────────
        editor_page = Adw.PreferencesPage(title="Editor", icon_name="accessories-text-editor-symbolic")

        # Font group
        font_group = Adw.PreferencesGroup(title="Font")

        font_row = Adw.ActionRow(title="Font Family")
        self._font_entry = Gtk.Entry(text=self._settings["font-family"])
        self._font_entry.set_valign(Gtk.Align.CENTER)
        font_row.add_suffix(self._font_entry)
        font_group.add(font_row)

        size_row = Adw.SpinRow(
            title="Font Size",
            subtitle="Points",
        )
        adj = Gtk.Adjustment(
            value=self._settings["font-size"],
            lower=8,
            upper=32,
            step_increment=1,
        )
        size_row.set_adjustment(adj)
        font_group.add(size_row)

        editor_page.add(font_group)

        # Editing group
        editing_group = Adw.PreferencesGroup(title="Editing")

        tab_row = Adw.SpinRow(title="Tab Width", subtitle="Spaces per tab")
        tab_adj = Gtk.Adjustment(
            value=self._settings["tab-width"],
            lower=1,
            upper=8,
            step_increment=1,
        )
        tab_row.set_adjustment(tab_adj)
        editing_group.add(tab_row)

        wrap_row = Adw.SwitchRow(
            title="Word Wrap",
            subtitle="Wrap long lines at word boundaries",
        )
        wrap_row.set_active(self._settings["word-wrap"])
        editing_group.add(wrap_row)

        lines_row = Adw.SwitchRow(
            title="Line Numbers",
            subtitle="Show line numbers in the gutter",
        )
        lines_row.set_active(self._settings["line-numbers"])
        editing_group.add(lines_row)

        editor_page.add(editing_group)

        # Auto-save group
        autosave_group = Adw.PreferencesGroup(title="Auto-save")

        autosave_row = Adw.SwitchRow(
            title="Auto-save",
            subtitle="Automatically save changes",
        )
        autosave_row.set_active(self._settings["auto-save"])
        autosave_group.add(autosave_row)

        autosave_delay_row = Adw.SpinRow(
            title="Auto-save Delay",
            subtitle="Seconds between saves",
        )
        delay_adj = Gtk.Adjustment(
            value=self._settings["auto-save-delay"],
            lower=5,
            upper=300,
            step_increment=5,
        )
        autosave_delay_row.set_adjustment(delay_adj)
        autosave_group.add(autosave_delay_row)

        editor_page.add(autosave_group)

        self.add(editor_page)

        # Apply button
        apply_btn = Gtk.Button(label="Apply", halign=Gtk.Align.END)
        apply_btn.add_css_class("suggested-action")
        apply_btn.set_margin_end(16)
        apply_btn.set_margin_bottom(16)

        def on_apply(_):
            self._settings["font-family"] = self._font_entry.get_text()
            self._settings["font-size"] = int(size_row.get_value())
            self._settings["tab-width"] = int(tab_row.get_value())
            self._settings["word-wrap"] = wrap_row.get_active()
            self._settings["line-numbers"] = lines_row.get_active()
            self._settings["auto-save"] = autosave_row.get_active()
            self._settings["auto-save-delay"] = int(autosave_delay_row.get_value())
            self._apply_to_editor()
            self.close()

        apply_btn.connect("clicked", on_apply)
        editor_page.set_header_suffix(apply_btn)

    def _apply_to_editor(self):
        s = self._settings
        self._editor.set_font(s["font-family"], s["font-size"])
        self._editor.set_tab_width(s["tab-width"])
        self._editor.set_word_wrap(s["word-wrap"])
        self._editor.set_line_numbers(s["line-numbers"])
