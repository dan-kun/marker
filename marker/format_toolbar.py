"""Markdown format toolbar widget."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


class FormatToolbar(Gtk.Box):
    """Horizontal toolbar with linked button groups for Markdown formatting."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self._build_ui()

    def _build_ui(self):
        # Letters where Markdown users expect letters (B, I, H1, </>), and
        # symbolic icons for the rest. No emoji: they ignore the theme.
        inline = Gtk.Box()
        inline.add_css_class("linked")
        inline.append(self._btn(markup="<b>B</b>", tip="Bold (Ctrl+B)", action="win.format-bold"))
        inline.append(self._btn(markup="<i>I</i>", tip="Italic (Ctrl+I)", action="win.format-italic"))
        inline.append(self._btn(markup="<tt>&lt;/&gt;</tt>", tip="Code (Ctrl+`)",
                                action="win.format-code"))
        inline.append(self._btn(icon="insert-link-symbolic", tip="Link (Ctrl+L)",
                                action="win.format-link"))
        self.append(inline)

        headings = Gtk.Box()
        headings.add_css_class("linked")
        for level in (1, 2, 3):
            headings.append(self._btn(markup=f"H{level}", tip=f"Heading {level}",
                                      action="win.format-heading",
                                      target=GLib.Variant("i", level)))
        self.append(headings)

        lists = Gtk.Box()
        lists.add_css_class("linked")
        lists.append(self._btn(icon="view-list-bullet-symbolic", tip="Bullet list",
                               action="win.format-bullet-list"))
        lists.append(self._btn(icon="view-list-ordered-symbolic", tip="Numbered list",
                               action="win.format-numbered-list"))
        self.append(lists)

    def _btn(
        self,
        *,
        tip: str,
        action: str,
        icon: str | None = None,
        markup: str | None = None,
        target: GLib.Variant | None = None,
    ) -> Gtk.Button:
        # Only set the property that was given: icon_name=None triggers a
        # Gtk-CRITICAL in gtk_button_set_icon_name().
        btn = Gtk.Button(tooltip_text=tip, action_name=action)
        if icon:
            btn.set_icon_name(icon)
        elif markup:
            btn.set_child(Gtk.Label(label=markup, use_markup=True, width_chars=2))
        if target is not None:
            btn.set_action_target_value(target)
        return btn
