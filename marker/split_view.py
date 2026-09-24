"""Split view panel: editor + preview with debounced sync."""

from typing import Literal

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from .utils import Debouncer

Mode = Literal["editor", "split", "preview"]
MODES: tuple[Mode, ...] = ("editor", "split", "preview")


class SplitView(Gtk.Paned):
    """Horizontal paned widget managing editor/preview visibility."""

    def __init__(self, editor, preview):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)

        self._editor = editor
        self._preview = preview
        self._mode: Mode = "split"
        self._scroll_source = 0

        self._debouncer = Debouncer(300, self._do_render)

        self.set_start_child(editor)
        self.set_end_child(preview)
        self.set_resize_start_child(True)
        self.set_resize_end_child(True)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)

        # Set initial split position once the widget is allocated
        self.connect("realize", self._on_realize)

        vadj = editor.get_vadjustment()
        self._handlers = [
            (editor, editor.connect("content-changed", self._on_content_changed)),
            (vadj, vadj.connect("value-changed", self._on_editor_scrolled)),
        ]

    def dispose(self):
        self._debouncer.cancel()
        if self._scroll_source:
            GLib.source_remove(self._scroll_source)
            self._scroll_source = 0
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers = []

    def _on_realize(self, widget):
        def _set_initial_position():
            width = self.get_width()
            if width > 0:
                self.set_position(width // 2)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_set_initial_position)

    def _on_content_changed(self, editor):
        if self._mode != "editor":
            self._debouncer.trigger()

    def _do_render(self):
        self._preview.render(self._editor.get_text())

    def _on_editor_scrolled(self, vadj):
        # Coalesce bursts of scroll events into one JS call per frame.
        if self._mode == "split" and not self._scroll_source:
            self._scroll_source = GLib.timeout_add(16, self._sync_scroll)

    def _sync_scroll(self):
        self._scroll_source = 0
        vadj = self._editor.get_vadjustment()
        span = vadj.get_upper() - vadj.get_lower() - vadj.get_page_size()
        fraction = (vadj.get_value() - vadj.get_lower()) / span if span > 0 else 0.0
        self._preview.scroll_to_fraction(min(1.0, max(0.0, fraction)))
        return GLib.SOURCE_REMOVE

    def set_mode(self, mode: Mode):
        if mode not in MODES:
            raise ValueError(f"unknown view mode: {mode}")
        self._mode = mode
        self._editor.set_visible(mode != "preview")
        self._preview.set_visible(mode != "editor")
        if mode != "editor":
            self._debouncer.cancel()
            self._do_render()

    def get_mode(self) -> Mode:
        return self._mode
