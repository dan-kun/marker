"""Markdown format toolbar widget."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib


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
        # Inline: Bold, Italic
        inline = Gtk.Box()
        inline.add_css_class("linked")
        inline.append(self._btn(icon="format-text-bold-symbolic",
                                tip="Bold (Ctrl+B)", action="win.format-bold"))
        inline.append(self._btn(icon="format-text-italic-symbolic",
                                tip="Italic (Ctrl+I)", action="win.format-italic"))
        self.append(inline)

        # Headings: H1, H2
        headings = Gtk.Box()
        headings.add_css_class("linked")
        for level in (1, 2):
            headings.append(self._btn(label=f"H{level}",
                                      tip=f"Heading {level}",
                                      action="win.format-heading",
                                      target=GLib.Variant("i", level)))
        self.append(headings)

        # Block / structure: code, bullet, numbered, link
        block = Gtk.Box()
        block.add_css_class("linked")
        block.append(self._btn(label="</>", tip="Code (Ctrl+`)",
                               action="win.format-code"))
        block.append(self._btn(label="•", tip="Bullet list",
                               action="win.format-bullet-list"))
        block.append(self._btn(label="1.", tip="Numbered list",
                               action="win.format-numbered-list"))
        block.append(self._btn(label="🔗", tip="Link (Ctrl+L)",
                               action="win.format-link"))
        self.append(block)

    def _btn(
        self,
        *,
        tip: str,
        action: str,
        icon: str | None = None,
        label: str | None = None,
        target: GLib.Variant | None = None,
    ) -> Gtk.Button:
        btn = Gtk.Button(
            icon_name=icon if icon else None,
            label=label if label else None,
            tooltip_text=tip,
        )
        btn.set_action_name(action)
        if target is not None:
            btn.set_action_target_value(target)
        return btn
