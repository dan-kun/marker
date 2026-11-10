"""Split view panel: editor + preview with debounced sync."""

import itertools
from typing import Literal

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from .utils import Debouncer

_doc_ids = itertools.count(1)

Mode = Literal["editor", "split", "preview"]
MODES: tuple[Mode, ...] = ("editor", "split", "preview")


class SplitView(Gtk.Paned):
    """One tab's content: its editor, plus the window's shared preview while
    the tab is active (see attach_preview / detach_preview)."""

    def __init__(self, editor, mode: Mode = "split"):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)

        self._editor = editor
        self._preview = None
        self._mode: Mode = mode
        self._base_dir: str | None = None
        self.doc_id = next(_doc_ids)  # the preview keeps a scroll position per document
        self._preview_is_stale = True  # the preview shows another tab's document
        self._scroll_source = 0

        self._debouncer = Debouncer(300, self._do_render)

        self.set_start_child(editor)
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
        self.detach_preview()
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

    # ── Shared preview ─────────────────────────────────────────────────────

    def attach_preview(self, preview):
        """Show the shared preview in this tab and point it at this document."""
        self._preview = preview
        self.set_end_child(preview)
        preview.set_zoom(self._editor.zoom_level)
        self._preview_is_stale = True
        self._apply_mode()

    def detach_preview(self):
        """Give the preview up so another tab can use it."""
        preview, self._preview = self._preview, None
        if preview is None:
            return
        self._debouncer.cancel()
        self.set_end_child(None)

    def set_base_dir(self, directory: str | None):
        """Folder that relative links and images in the document resolve against."""
        self._base_dir = directory
        if self._preview is not None and not self._preview_is_stale:
            self._preview.set_base_dir(directory)

    # ── Rendering and scroll sync ──────────────────────────────────────────

    def _on_content_changed(self, editor):
        if self._preview is not None and self._mode != "editor":
            self._debouncer.trigger()

    def _do_render(self):
        if self._preview is not None:
            self._preview.render(self._editor.get_text())

    def _editor_scroll_fraction(self) -> float:
        vadj = self._editor.get_vadjustment()
        span = vadj.get_upper() - vadj.get_lower() - vadj.get_page_size()
        fraction = (vadj.get_value() - vadj.get_lower()) / span if span > 0 else 0.0
        return min(1.0, max(0.0, fraction))

    def _on_editor_scrolled(self, vadj):
        # Coalesce bursts of scroll events into one JS call per frame.
        if self._preview is not None and self._mode == "split" and not self._scroll_source:
            self._scroll_source = GLib.timeout_add(16, self._sync_scroll)

    def _sync_scroll(self):
        self._scroll_source = 0
        if self._preview is not None:
            self._preview.scroll_to_line(self._editor.get_top_line(), self._editor_scroll_fraction())
        return GLib.SOURCE_REMOVE

    # ── View mode ──────────────────────────────────────────────────────────

    def _apply_mode(self):
        self._editor.set_visible(self._mode != "preview")
        if self._preview is None:
            return
        self._preview.set_visible(self._mode != "editor")
        if self._mode == "editor":
            return  # hidden: rendered when it becomes visible
        self._debouncer.cancel()
        if self._preview_is_stale:
            self._preview_is_stale = False
            # Split view follows the editor; preview-only returns to where
            # the reader left this document.
            scroll = None
            if self._mode == "split":
                scroll = (self._editor.get_top_line(), self._editor_scroll_fraction())
            self._preview.show_document(
                self.doc_id, self._editor.get_text(), self._base_dir, scroll
            )
        else:
            self._do_render()

    def set_mode(self, mode: Mode):
        if mode not in MODES:
            raise ValueError(f"unknown view mode: {mode}")
        self._mode = mode
        self._apply_mode()

    def get_mode(self) -> Mode:
        return self._mode
