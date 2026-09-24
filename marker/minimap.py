"""Document minimap: scaled silhouette of the editor content."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from .utils import Debouncer

# Adwaita blue 3, readable on both light and dark backgrounds
_ACCENT = (0.21, 0.52, 0.89)


def outline(text: str) -> list[tuple[bool, float]]:
    """Return (is_heading, relative_width) per line of text.

    "#" lines inside fenced code blocks are not headings.
    """
    lines = text.split("\n")
    max_len = max((len(line) for line in lines), default=0) or 1
    result = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            is_heading = False
        else:
            is_heading = not in_fence and stripped.startswith("#")
        result.append((is_heading, len(line) / max_len))
    return result


class Minimap(Gtk.DrawingArea):
    """
    Scaled-down silhouette of the active editor's buffer.
    - Headings → taller, stronger bar
    - Body lines → thin bar, width proportional to line length
    - Viewport indicator → accent-colored translucent rectangle
    """

    WIDGET_WIDTH = 80
    LINE_HEIGHT = 3      # pixels per line in minimap
    HEADING_HEIGHT = 5   # pixels for heading lines
    TOP_MARGIN = 2

    def __init__(self):
        super().__init__()
        self.set_size_request(self.WIDGET_WIDTH, -1)
        self.set_vexpand(True)
        self.set_draw_func(self._on_draw)

        self._lines: list[tuple[bool, float]] = []
        self._viewport_top = 0.0     # 0..1 fraction of the document
        self._viewport_height = 1.0  # 0..1 fraction of the document

        self._editor = None
        self._handlers: list = []  # (object, handler id) on the current editor
        self._rebuild = Debouncer(150, self._rebuild_lines)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.connect("drag-update", self._on_drag)
        self.add_controller(drag)

    def set_editor(self, editor):
        """Connect minimap to a new editor (call when active tab changes)."""
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers = []
        self._rebuild.cancel()
        self._editor = editor

        if editor is None:
            self._lines = []
            self.queue_draw()
            return

        buf = editor.get_buffer()
        vadj = editor.get_vadjustment()
        self._handlers = [
            (buf, buf.connect("changed", lambda *_: self._rebuild.trigger())),
            (vadj, vadj.connect("value-changed", self._on_vadj_changed)),
            (vadj, vadj.connect("notify::upper", self._on_vadj_changed)),
            (vadj, vadj.connect("notify::page-size", self._on_vadj_changed)),
        ]
        self._on_vadj_changed(vadj)
        self._rebuild_lines()

    def _rebuild_lines(self):
        if self._editor is None:
            return
        self._lines = outline(self._editor.get_text())
        self.queue_draw()

    def _on_vadj_changed(self, vadj, *_):
        lo, hi = vadj.get_lower(), vadj.get_upper()
        total = hi - lo
        if total <= 0:
            self._viewport_top, self._viewport_height = 0.0, 1.0
        else:
            self._viewport_top = (vadj.get_value() - lo) / total
            self._viewport_height = min(1.0, vadj.get_page_size() / total)
        self.queue_draw()

    def _layout(self, height: int) -> tuple[float, float]:
        """(scale, content_height): lines shrink to fit when the document is
        taller than the widget; short documents only use the top part."""
        natural = sum(self.HEADING_HEIGHT if h else self.LINE_HEIGHT for h, _ in self._lines)
        usable = max(1, height - self.TOP_MARGIN)
        scale = usable / natural if natural > usable else 1.0
        return scale, natural * scale

    def _foreground(self):
        if hasattr(self, "get_color"):  # GTK ≥ 4.10
            color = self.get_color()
        else:
            color = self.get_style_context().get_color()
        return color.red, color.green, color.blue

    def _on_draw(self, area, cr, width, height):
        if not self._lines:
            return
        r, g, b = self._foreground()
        scale, content_h = self._layout(height)

        y = float(self.TOP_MARGIN)
        for is_heading, rel_width in self._lines:
            lh = (self.HEADING_HEIGHT if is_heading else self.LINE_HEIGHT) * scale
            if rel_width > 0:
                cr.set_source_rgba(r, g, b, 0.85 if is_heading else 0.35)
                cr.rectangle(4, y, rel_width * (width - 8), max(lh - 0.5, 0.5))
                cr.fill()
            y += lh

        # Viewport indicator, mapped onto the drawn lines (not the widget)
        vp_y = self.TOP_MARGIN + self._viewport_top * content_h
        vp_h = max(4.0, self._viewport_height * content_h)
        cr.set_source_rgba(*_ACCENT, 0.18)
        cr.rectangle(0, vp_y, width, vp_h)
        cr.fill()
        cr.set_source_rgba(*_ACCENT, 0.6)
        cr.set_line_width(1.0)
        cr.rectangle(0.5, vp_y + 0.5, width - 1, max(vp_h - 1, 1))
        cr.stroke()

    def _on_click(self, gesture, n_press, x, y):
        self._scroll_to_y(y)

    def _on_drag(self, gesture, dx, dy):
        ok, start_x, start_y = gesture.get_start_point()
        if ok:
            self._scroll_to_y(start_y + dy)

    def _scroll_to_y(self, y):
        if self._editor is None or not self._lines:
            return
        _, content_h = self._layout(self.get_height())
        if content_h <= 0:
            return
        frac = max(0.0, min(1.0, (y - self.TOP_MARGIN) / content_h))
        vadj = self._editor.get_vadjustment()
        lo, hi, page = vadj.get_lower(), vadj.get_upper(), vadj.get_page_size()
        # Center the viewport on the clicked point
        vadj.set_value(max(lo, min(hi - page, lo + frac * (hi - lo) - page / 2)))
