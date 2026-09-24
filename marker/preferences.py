"""Preferences window. Changes apply immediately and are saved to disk.

Built from Adw.ActionRow + Gtk widgets rather than Adw.SpinRow/SwitchRow
so it works with libadwaita 1.1.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from .settings import Settings


def _action_row(title, subtitle, widget) -> Adw.ActionRow:
    widget.set_valign(Gtk.Align.CENTER)
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    row.add_suffix(widget)
    row.set_activatable_widget(widget)
    return row


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, settings: Settings, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Preferences")
        self.set_default_size(480, 520)
        self.set_search_enabled(False)
        self._settings = settings
        self._build_ui()

    def _spin(self, key: str, lo: int, hi: int, step: int = 1) -> Gtk.SpinButton:
        adj = Gtk.Adjustment(value=self._settings[key], lower=lo, upper=hi,
                             step_increment=step, page_increment=step * 4)
        spin = Gtk.SpinButton(adjustment=adj, digits=0, width_chars=5)
        spin.connect("value-changed", lambda s: self._set(key, int(s.get_value())))
        return spin

    def _switch(self, key: str) -> Gtk.Switch:
        switch = Gtk.Switch(active=self._settings[key])
        switch.connect("notify::active", lambda s, _: self._set(key, s.get_active()))
        return switch

    def _set(self, key, value):
        self._settings[key] = value
        if key == "auto-save":
            self._auto_save_delay_row.set_sensitive(value)

    def _build_ui(self):
        page = Adw.PreferencesPage(title="Editor", icon_name="accessories-text-editor-symbolic")

        font_group = Adw.PreferencesGroup(title="Font")
        font_entry = Gtk.Entry(text=self._settings["font-family"], width_chars=16)
        # Apply when the user finishes typing, not on every keystroke
        font_entry.connect("activate", self._on_font_family_done)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda c: self._on_font_family_done(font_entry))
        font_entry.add_controller(focus)
        font_group.add(_action_row("Font Family", "Editor font name, e.g. “DejaVu Sans Mono”", font_entry))
        font_group.add(_action_row("Font Size", "Size in points", self._spin("font-size", 8, 32)))
        page.add(font_group)

        edit_group = Adw.PreferencesGroup(title="Editing")
        edit_group.add(_action_row("Tab Width", "Spaces per tab", self._spin("tab-width", 1, 8)))
        edit_group.add(_action_row("Word Wrap", "Wrap long lines at word boundaries",
                                   self._switch("word-wrap")))
        edit_group.add(_action_row("Line Numbers", "Show line numbers in the gutter",
                                   self._switch("line-numbers")))
        page.add(edit_group)

        save_group = Adw.PreferencesGroup(
            title="Auto-save",
            description="Only files that already have a name are saved automatically.",
        )
        save_group.add(_action_row("Auto-save", "Save changes after you stop typing",
                                   self._switch("auto-save")))
        self._auto_save_delay_row = _action_row(
            "Delay", "Seconds of inactivity before saving", self._spin("auto-save-delay", 5, 300, step=5)
        )
        self._auto_save_delay_row.set_sensitive(self._settings["auto-save"])
        save_group.add(self._auto_save_delay_row)
        page.add(save_group)

        self.add(page)

    def _on_font_family_done(self, entry):
        self._settings["font-family"] = entry.get_text().strip() or "Monospace"
