"""Split view panel: editor + preview with debounced sync."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk
from .utils import Debouncer

Mode = str  # "editor" | "split" | "preview"


class SplitView(Gtk.Paned):
    """Horizontal paned widget managing editor/preview visibility."""

    def __init__(self, editor, preview):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)

        self._editor = editor
        self._preview = preview
        self._mode: Mode = "split"

        self._debouncer = Debouncer(300, self._do_render)

        self.set_start_child(editor)
        self.set_end_child(preview)
        self.set_resize_start_child(True)
        self.set_resize_end_child(True)
        self.set_shrink_start_child(False)
        self.set_shrink_end_child(False)

        # Set initial split position once the widget is allocated
        self.connect("realize", self._on_realize)

        # Connect to editor changes for preview updates
        editor.connect("content-changed", self._on_content_changed)

    def _on_realize(self, widget):
        # Set 50/50 split after the widget knows its actual width
        def _set_initial_position():
            w = self.get_allocated_width()
            if w > 0:
                self.set_position(w // 2)
            return False  # don't repeat
        from gi.repository import GLib
        GLib.idle_add(_set_initial_position)

    def _on_content_changed(self, editor, text):
        if self._mode in ("split", "preview"):
            self._debouncer.trigger(text)

    def _do_render(self, text: str):
        self._preview.render(text)

    def set_mode(self, mode: Mode):
        self._mode = mode
        match mode:
            case "editor":
                self._editor.set_visible(True)
                self._preview.set_visible(False)
            case "preview":
                self._editor.set_visible(False)
                self._preview.set_visible(True)
                # Render current content
                text = self._editor.get_text()
                self._preview.render(text)
            case "split":
                self._editor.set_visible(True)
                self._preview.set_visible(True)
                # Render current content
                text = self._editor.get_text()
                self._preview.render(text)

    def get_mode(self) -> Mode:
        return self._mode
