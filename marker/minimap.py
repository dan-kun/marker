"""Document minimap: scaled silhouette of the editor content."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GObject


class Minimap(Gtk.DrawingArea):
    """
    Scaled-down silhouette of the active editor's buffer.
    - Headings (lines starting with #) → taller, darker bar
    - Body lines → 2px mid-gray bar, width proportional to line length
    - Viewport indicator → accent-colored translucent rectangle
    """

    WIDGET_WIDTH = 80
    LINE_HEIGHT = 3      # pixels per line in minimap
    HEADING_HEIGHT = 5   # pixels for heading lines
    MAX_LINE_WIDTH = 70  # max bar width in pixels

    def __init__(self):
        super().__init__()
        self.set_size_request(self.WIDGET_WIDTH, -1)
        self.set_vexpand(True)
        self.set_draw_func(self._on_draw)

        self._lines: list = []             # list of (is_heading: bool, norm_width: float)
        self._viewport_top: float = 0.0    # 0..1 fraction
        self._viewport_height: float = 0.1  # 0..1 fraction

        self._editor = None
        self._buffer_handler = 0
        self._vadj_handler = 0

        # Click/drag to scroll
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.connect("drag-update", self._on_drag)
        self.add_controller(drag)

    def set_editor(self, editor):
        """Connect minimap to a new editor (call when active tab changes)."""
        # Disconnect from old editor
        if self._editor is not None:
            old_buf = self._editor.get_buffer()
            if self._buffer_handler:
                old_buf.disconnect(self._buffer_handler)
                self._buffer_handler = 0
            old_adj = self._editor.get_vadjustment()
            if old_adj and self._vadj_handler:
                old_adj.disconnect(self._vadj_handler)
                self._vadj_handler = 0

        self._editor = editor

        if editor is None:
            self._lines = []
            self.queue_draw()
            return

        buf = editor.get_buffer()
        self._buffer_handler = buf.connect("changed", self._on_buffer_changed)

        vadj = editor.get_vadjustment()
        if vadj:
            self._vadj_handler = vadj.connect("value-changed", self._on_vadj_changed)
            self._on_vadj_changed(vadj)

        self._rebuild_lines()

    def _rebuild_lines(self):
        if self._editor is None:
            return
        buf = self._editor.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        text = buf.get_text(start, end, True)
        lines = text.split("\n")

        max_len = max((len(line) for line in lines), default=1) or 1
        self._lines = []
        for line in lines:
            is_heading = line.startswith("#")
            width = min(len(line) / max_len, 1.0)
            self._lines.append((is_heading, width))

        self.queue_draw()

    def _on_buffer_changed(self, buf):
        self._rebuild_lines()

    def _on_vadj_changed(self, vadj):
        lo = vadj.get_lower()
        hi = vadj.get_upper()
        page = vadj.get_page_size()
        val = vadj.get_value()
        total = hi - lo
        if total <= 0:
            self._viewport_top = 0.0
            self._viewport_height = 1.0
        else:
            self._viewport_top = val / total
            self._viewport_height = page / total
        self.queue_draw()

    def _on_draw(self, area, cr, width, height):
        # Background
        style = self.get_style_context()
        Gtk.render_background(style, cr, 0, 0, width, height)

        if not self._lines:
            return

        total_h = sum(
            self.HEADING_HEIGHT if is_h else self.LINE_HEIGHT
            for is_h, _ in self._lines
        )

        # Scale factor: map total_h → widget height
        scale = height / total_h if total_h > height else 1.0

        # Draw lines
        y = 2.0
        for is_heading, norm_w in self._lines:
            lh = (self.HEADING_HEIGHT if is_heading else self.LINE_HEIGHT) * scale
            bar_w = norm_w * (width - 8)

            if is_heading:
                cr.set_source_rgba(0.2, 0.2, 0.2, 0.9)
            else:
                cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)

            cr.rectangle(4, y, bar_w, max(lh - 0.5, 1.0))
            cr.fill()
            y += lh

        # Viewport indicator
        vp_y = self._viewport_top * height
        vp_h = self._viewport_height * height
        cr.set_source_rgba(0.4, 0.6, 1.0, 0.2)
        cr.rectangle(0, vp_y, width, vp_h)
        cr.fill()
        cr.set_source_rgba(0.4, 0.6, 1.0, 0.6)
        cr.set_line_width(1.0)
        cr.rectangle(0.5, vp_y + 0.5, width - 1, vp_h - 1)
        cr.stroke()

    def _on_click(self, gesture, n_press, x, y):
        self._scroll_to_y(y)

    def _on_drag(self, gesture, dx, dy):
        ok, start_x, start_y = gesture.get_start_point()
        if ok:
            self._scroll_to_y(start_y + dy)

    def _scroll_to_y(self, y):
        if self._editor is None:
            return
        h = self.get_allocated_height()
        if h <= 0:
            return
        frac = max(0.0, min(1.0, y / h))
        vadj = self._editor.get_vadjustment()
        if vadj:
            lo = vadj.get_lower()
            hi = vadj.get_upper()
            page = vadj.get_page_size()
            vadj.set_value(lo + frac * (hi - lo - page))
