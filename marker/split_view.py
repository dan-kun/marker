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


class Divider:
    """Where the editor/preview divider sits, as the editor's share of the
    width. A window's tabs share one, so the divider is in the same place
    whichever tab is showing."""

    def __init__(self, fraction: float = 0.5):
        self.fraction = fraction


class SplitView(Gtk.Paned):
    """One tab's content: its editor, plus the window's shared preview while
    the tab is active (see attach_preview / detach_preview)."""

    def __init__(self, editor, mode: Mode = "split", divider: Divider | None = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)

        self._editor = editor
        self._preview = None
        self._mode: Mode = mode
        self._base_dir: str | None = None
        self._syntax: str | None = None  # None: Markdown; else shown as source text
        self._divider = divider or Divider()
        self._divider_placed = False
        self.doc_id = next(_doc_ids)  # the preview keeps a scroll position per document
        self._preview_is_stale = True  # the preview shows another tab's document
        self._scroll_source = 0

        self._debouncer = Debouncer(300, self._do_render)

        self.set_start_child(editor)
        self.set_resize_start_child(True)
        self.set_resize_end_child(True)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)

        vadj = editor.get_vadjustment()
        self._handlers = [
            (editor, editor.connect("content-changed", self._on_content_changed)),
            (vadj, vadj.connect("value-changed", self._on_editor_scrolled)),
            (self, self.connect("notify::position", self._on_divider_moved)),
        ]

    def dispose(self):
        self.detach_preview()
        if self._scroll_source:
            GLib.source_remove(self._scroll_source)
            self._scroll_source = 0
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers = []

    # ── Divider ────────────────────────────────────────────────────────────

    def _shows_both(self) -> bool:
        return self._preview is not None and self._mode == "split"

    def do_size_allocate(self, width: int, height: int, baseline: int):
        # The divider is placed here, when the real width is known. A tab
        # opened in the background has no size until it is first shown, and
        # a position computed any earlier leaves the preview 1 px wide.
        if not self._divider_placed and width > 0 and self._shows_both():
            self._divider_placed = True
            self.set_position(round(width * self._divider.fraction))
        Gtk.Paned.do_size_allocate(self, width, height, baseline)

    def _on_divider_moved(self, *_):
        width = self.get_width()
        if self._divider_placed and width > 0 and self._shows_both():
            self._divider.fraction = min(0.9, max(0.1, self.get_position() / width))

    # ── Shared preview ─────────────────────────────────────────────────────

    def attach_preview(self, preview):
        """Show the shared preview in this tab and point it at this document."""
        self._preview = preview
        self.set_end_child(preview)
        preview.set_zoom(self._editor.zoom_level)
        self._preview_is_stale = True
        self._divider_placed = False  # another tab may have moved it
        self._apply_mode()

    def detach_preview(self):
        """Give the preview up so another tab can use it."""
        preview, self._preview = self._preview, None
        if preview is None:
            return
        self._debouncer.cancel()
        self.set_end_child(None)

    def set_document(self, directory: str | None, syntax: str | None):
        """What the preview needs to know about the file: the folder that
        relative links and images resolve against, and whether to render it
        as Markdown (syntax None) or show it as source text in that language."""
        self._base_dir = directory
        syntax_changed, self._syntax = syntax != self._syntax, syntax
        if self._preview is None or self._preview_is_stale:
            return
        self._preview.set_base_dir(directory, rerender=not syntax_changed)
        if syntax_changed and self._mode != "editor":
            self._do_render()

    # ── Rendering and scroll sync ──────────────────────────────────────────

    def _on_content_changed(self, editor):
        if self._preview is not None and self._mode != "editor":
            self._debouncer.trigger()

    def _do_render(self):
        if self._preview is not None:
            self._preview.render(self._editor.get_text(), syntax=self._syntax)

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
                self.doc_id, self._editor.get_text(), self._base_dir, scroll, self._syntax
            )
        else:
            self._do_render()

    def set_mode(self, mode: Mode):
        if mode not in MODES:
            raise ValueError(f"unknown view mode: {mode}")
        had_focus = self.get_focus_child() is not None
        self._mode = mode
        self._apply_mode()
        if mode == "split":
            self.queue_allocate()  # place the divider if this tab never showed both
        if had_focus:
            # Hiding the pane that had the keyboard focus would leave it nowhere
            (self._preview if mode == "preview" and self._preview else self._editor).grab_focus()

    def get_mode(self) -> Mode:
        return self._mode
