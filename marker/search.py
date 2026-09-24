"""Search bar: in-file (GtkSourceSearchContext) and cross-file (grep)."""

import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, GtkSource, Pango

from .filetypes import SHOWN_EXTENSIONS

MAX_DIR_RESULTS = 200
MAX_MATCHES_PER_FILE = 5


def parse_grep_output(data: bytes, limit: int = MAX_DIR_RESULTS) -> tuple[list[tuple[str, int, str]], int]:
    """Parse `grep -rnZ` output into ([(path, line, text)], total_count).

    With -Z the file name ends in a NUL byte, so paths containing ':' parse
    correctly. Lines are decoded leniently since files may not be UTF-8.
    """
    results = []
    total = 0
    for raw in data.split(b"\n"):
        path, sep, rest = raw.partition(b"\0")
        if not sep:
            continue
        lineno, sep, text = rest.partition(b":")
        if not sep or not lineno.isdigit():
            continue
        total += 1
        if len(results) < limit:
            results.append((
                os.fsdecode(path),
                int(lineno),
                text.decode("utf-8", errors="replace").strip(),
            ))
    return results, total


class SearchBar(Gtk.Box):
    """Combined in-file search/replace + directory search bar."""

    __gsignals__ = {
        # (path, 0-based line) of a "Find in Folder" result the user picked
        "open-location": (GObject.SignalFlags.RUN_LAST, None, (str, int)),
    }

    def __init__(self, editor, root_provider: Callable[[], str | None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._editor = None
        self._buffer = None
        self._root_provider = root_provider
        self._search_ctx: GtkSource.SearchContext | None = None
        self._count_handler = 0
        self._search_settings = GtkSource.SearchSettings()
        self._search_settings.set_wrap_around(True)
        self._grep_cancellable: Gio.Cancellable | None = None

        self._build_ui()
        self.set_editor(editor)
        self.set_visible(False)

    def _build_ui(self):
        # ── In-file search/replace ─────────────────────────────────────────
        self._inline_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._inline_bar.set_margin_start(8)
        self._inline_bar.set_margin_end(8)
        self._inline_bar.set_margin_top(4)
        self._inline_bar.set_margin_bottom(4)

        search_row = Gtk.Box(spacing=4)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Find…")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", lambda *_: self._do_search())
        self._search_entry.connect("activate", self._on_find_next)
        self._search_entry.connect("next-match", self._on_find_next)
        self._search_entry.connect("previous-match", self._on_find_prev)
        self._search_entry.connect("stop-search", self._on_close)
        self._add_shift_enter(self._search_entry, self._on_find_prev)
        search_row.append(self._search_entry)

        btn_prev = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Previous (Shift+Enter)")
        btn_prev.add_css_class("flat")
        btn_prev.connect("clicked", self._on_find_prev)
        search_row.append(btn_prev)

        btn_next = Gtk.Button(icon_name="go-down-symbolic", tooltip_text="Next (Enter)")
        btn_next.add_css_class("flat")
        btn_next.connect("clicked", self._on_find_next)
        search_row.append(btn_next)

        self._btn_case = Gtk.ToggleButton(label="Aa", tooltip_text="Match case")
        self._btn_case.add_css_class("flat")
        self._btn_case.connect("toggled", self._on_options_changed)
        search_row.append(self._btn_case)

        self._btn_regex = Gtk.ToggleButton(label=".*", tooltip_text="Use regular expression")
        self._btn_regex.add_css_class("flat")
        self._btn_regex.connect("toggled", self._on_options_changed)
        search_row.append(self._btn_regex)

        self._match_label = Gtk.Label(label="", width_chars=10)
        self._match_label.add_css_class("dim-label")
        self._match_label.add_css_class("caption")
        search_row.append(self._match_label)

        btn_close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Close (Esc)")
        btn_close.add_css_class("flat")
        btn_close.connect("clicked", self._on_close)
        search_row.append(btn_close)

        self._inline_bar.append(search_row)

        # Replace row (hidden by default)
        self._replace_row = Gtk.Box(spacing=4)
        self._replace_entry = Gtk.Entry(placeholder_text="Replace with…")
        self._replace_entry.set_hexpand(True)
        self._replace_entry.connect("activate", self._on_replace)
        self._add_escape(self._replace_entry)
        self._replace_row.append(self._replace_entry)

        btn_replace = Gtk.Button(label="Replace")
        btn_replace.add_css_class("flat")
        btn_replace.connect("clicked", self._on_replace)
        self._replace_row.append(btn_replace)

        btn_replace_all = Gtk.Button(label="All")
        btn_replace_all.add_css_class("flat")
        btn_replace_all.connect("clicked", self._on_replace_all)
        self._replace_row.append(btn_replace_all)

        self._inline_bar.append(self._replace_row)
        self._replace_row.set_visible(False)
        self.append(self._inline_bar)

        # ── Directory search ───────────────────────────────────────────────
        self._dir_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._dir_bar.set_margin_start(8)
        self._dir_bar.set_margin_end(8)
        self._dir_bar.set_margin_top(4)
        self._dir_bar.set_margin_bottom(4)

        dir_search_row = Gtk.Box(spacing=4)

        self._dir_entry = Gtk.SearchEntry(placeholder_text="Search in all files…")
        self._dir_entry.set_hexpand(True)
        self._dir_entry.connect("activate", self._on_dir_search)
        self._dir_entry.connect("stop-search", self._on_close)
        dir_search_row.append(self._dir_entry)

        btn_dir_search = Gtk.Button(icon_name="system-search-symbolic", tooltip_text="Search")
        btn_dir_search.add_css_class("flat")
        btn_dir_search.connect("clicked", self._on_dir_search)
        dir_search_row.append(btn_dir_search)

        btn_dir_close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Close (Esc)")
        btn_dir_close.add_css_class("flat")
        btn_dir_close.connect("clicked", self._on_close)
        dir_search_row.append(btn_dir_close)

        self._dir_bar.append(dir_search_row)

        self._dir_results_scroll = Gtk.ScrolledWindow()
        self._dir_results_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._dir_results_scroll.set_max_content_height(200)
        self._dir_results_scroll.set_propagate_natural_height(True)

        self._dir_results = Gtk.ListBox()
        self._dir_results.add_css_class("boxed-list")
        self._dir_results.set_selection_mode(Gtk.SelectionMode.SINGLE)
        # Connected once here, not per row
        self._dir_results.connect("row-activated", self._on_dir_result_activated)
        self._dir_results_scroll.set_child(self._dir_results)
        self._dir_bar.append(self._dir_results_scroll)

        self._dir_bar.set_visible(False)
        self.append(self._dir_bar)

        self.append(Gtk.Separator())

    def _add_shift_enter(self, widget, callback):
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

        def on_key(ctrl, keyval, keycode, state):
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and state & Gdk.ModifierType.SHIFT_MASK:
                callback()
                return True
            return False

        controller.connect("key-pressed", on_key)
        widget.add_controller(controller)

    def _add_escape(self, widget):
        controller = Gtk.EventControllerKey()

        def on_key(ctrl, keyval, keycode, state):
            if keyval == Gdk.KEY_Escape:
                self._on_close()
                return True
            return False

        controller.connect("key-pressed", on_key)
        widget.add_controller(controller)

    # ── Public API ─────────────────────────────────────────────────────────

    def set_editor(self, editor):
        """Reconnect the search bar to a new editor (called on tab switch)."""
        if self._search_ctx is not None:
            self._search_ctx.disconnect(self._count_handler)
            self._search_ctx.set_highlight(False)
        self._editor = editor
        self._buffer = editor.get_buffer()
        self._search_ctx = GtkSource.SearchContext(
            buffer=self._buffer,
            settings=self._search_settings,
        )
        self._search_ctx.set_highlight(self.get_visible())
        # The count is computed asynchronously; -1 until the scan finishes.
        self._count_handler = self._search_ctx.connect(
            "notify::occurrences-count", lambda *_: self._update_match_count()
        )
        self._update_match_count()

    def show_search(self):
        self._show_inline(replace=False)

    def show_replace(self):
        self._show_inline(replace=True)

    def _show_inline(self, replace: bool):
        self._inline_bar.set_visible(True)
        self._replace_row.set_visible(replace)
        self._dir_bar.set_visible(False)
        self.set_visible(True)
        self._search_ctx.set_highlight(True)

        # Seed the query with a single-line selection, like most editors
        if self._buffer.get_has_selection():
            start, end = self._buffer.get_selection_bounds()
            selected = self._buffer.get_text(start, end, True)
            if selected and "\n" not in selected:
                self._search_entry.set_text(selected)
        self._search_entry.grab_focus()
        self._do_search()

    def show_dir_search(self):
        self._inline_bar.set_visible(False)
        self._dir_bar.set_visible(True)
        self.set_visible(True)
        self._dir_entry.grab_focus()

    # ── In-file search ─────────────────────────────────────────────────────

    def _on_close(self, *_):
        self.set_visible(False)
        self._search_settings.set_search_text(None)
        self._search_ctx.set_highlight(False)
        self._match_label.set_text("")
        if self._grep_cancellable is not None:
            self._grep_cancellable.cancel()
        self._editor.grab_focus()

    def _on_options_changed(self, *_):
        self._search_settings.set_case_sensitive(self._btn_case.get_active())
        self._search_settings.set_regex_enabled(self._btn_regex.get_active())
        self._do_search()

    def _do_search(self):
        text = self._search_entry.get_text()
        self._search_settings.set_search_text(text or None)
        self._update_match_count()

    def _has_query(self) -> bool:
        """Apply the entry's text now (search-changed fires after a delay)
        and report whether there is anything to search for."""
        text = self._search_entry.get_text()
        if text != (self._search_settings.get_search_text() or ""):
            self._do_search()
        return bool(text)

    def _update_match_count(self):
        label = self._match_label
        label.remove_css_class("error")
        if not self._search_settings.get_search_text():
            label.set_text("")
            return
        error = self._search_ctx.get_regex_error()
        count = self._search_ctx.get_occurrences_count()
        if error is not None:
            label.set_text("Invalid regex")
            label.add_css_class("error")
        elif count < 0:
            label.set_text("…")
        elif count == 0:
            label.set_text("No results")
            label.add_css_class("error")
        else:
            label.set_text(f"{count} found")

    def _search_origin(self, forward: bool):
        """Search from the end of the current selection when going forward,
        so that repeated "next" moves past the match that is selected."""
        buf = self._buffer
        if buf.get_has_selection():
            start, end = buf.get_selection_bounds()
            return end if forward else start
        return buf.get_iter_at_mark(buf.get_insert())

    def _select_match(self, start, end):
        self._buffer.select_range(start, end)
        self._editor.get_view().scroll_to_iter(start, 0.1, False, 0, 0)

    def _on_find_next(self, *_):
        if not self._has_query():
            return
        found, start, end, _ = self._search_ctx.forward(self._search_origin(forward=True))
        if found:
            self._select_match(start, end)

    def _on_find_prev(self, *_):
        if not self._has_query():
            return
        found, start, end, _ = self._search_ctx.backward(self._search_origin(forward=False))
        if found:
            self._select_match(start, end)

    def _on_replace(self, *_):
        """Replace the selected match (or the next one), then select the next."""
        if not self._has_query():
            return
        buf = self._buffer
        origin = buf.get_selection_bounds()[0] if buf.get_has_selection() else \
            buf.get_iter_at_mark(buf.get_insert())
        found, start, end, _ = self._search_ctx.forward(origin)
        if not found:
            return
        replacement = self._replace_entry.get_text()
        try:
            self._search_ctx.replace(start, end, replacement, -1)
        except GLib.Error:
            return  # invalid regex back-reference
        self._on_find_next()

    def _on_replace_all(self, *_):
        if not self._has_query():
            return
        try:
            self._search_ctx.replace_all(self._replace_entry.get_text(), -1)
        except GLib.Error:
            pass

    # ── Directory search ───────────────────────────────────────────────────

    def _on_dir_search(self, *_):
        query = self._dir_entry.get_text()
        if not query.strip():
            return

        root = self._root_provider()
        self._dir_results_clear()
        if not root:
            self._add_dir_result_label("Open a folder first to search in files.")
            return

        if self._grep_cancellable is not None:
            self._grep_cancellable.cancel()
        self._grep_cancellable = Gio.Cancellable()
        self._add_dir_result_label("Searching…")

        # -F: literal text, -e/--: the query can never be read as an option,
        # -I: skip binary files, -Z: NUL after the file name.
        argv = ["grep", "-rnIFZ", "-m", str(MAX_MATCHES_PER_FILE), "--exclude-dir=.*"]
        argv += [f"--include=*{ext}" for ext in sorted(SHOWN_EXTENSIONS)]
        argv += ["-e", query, "--", root]
        try:
            proc = Gio.Subprocess.new(
                argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
            )
        except GLib.Error as e:
            self._dir_results_clear()
            self._add_dir_result_label(f"Search failed: {e.message}")
            return
        proc.communicate_async(None, self._grep_cancellable, self._on_grep_done, root)

    def _on_grep_done(self, proc, result, root):
        try:
            _, stdout, _ = proc.communicate_finish(result)
        except GLib.Error as e:
            if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                self._dir_results_clear()
                self._add_dir_result_label(f"Search failed: {e.message}")
            return

        self._dir_results_clear()
        # grep exits with 1 for "no match" and 2 for errors such as unreadable files
        if proc.get_exit_status() == 2 and not stdout:
            self._add_dir_result_label("Search failed: grep could not read the folder.")
            return
        results, total = parse_grep_output(stdout.get_data() if stdout else b"")
        if not results:
            self._add_dir_result_label("No results found.")
            return
        for path, lineno, text in results:
            self._add_dir_result(path, lineno, text, root)
        if total > len(results):
            self._add_dir_result_label(f"… and {total - len(results)} more results.")

    def _dir_results_clear(self):
        while (row := self._dir_results.get_row_at_index(0)) is not None:
            self._dir_results.remove(row)

    def _add_dir_result_label(self, text: str):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("dim-label")
        label.set_margin_start(8)
        label.set_margin_end(8)
        label.set_margin_top(4)
        label.set_margin_bottom(4)
        row.set_child(label)
        self._dir_results.append(row)

    def _add_dir_result(self, path: str, lineno: int, text: str, root: str):
        row = Gtk.ListBoxRow()
        row.location = (path, lineno)  # type: ignore[attr-defined]

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        location = Gtk.Label(label=f"{os.path.relpath(path, root)}:{lineno}", xalign=0)
        location.add_css_class("caption")
        location.add_css_class("dim-label")
        location.set_ellipsize(Pango.EllipsizeMode.START)
        box.append(location)

        text_label = Gtk.Label(label=text[:200], xalign=0)
        text_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(text_label)

        row.set_child(box)
        row.set_tooltip_text(path)
        self._dir_results.append(row)

    def _on_dir_result_activated(self, listbox, row):
        location = getattr(row, "location", None)
        if location is not None:
            path, lineno = location
            self.emit("open-location", path, lineno - 1)
