"""Search bar: in-file (GtkSourceSearchContext) and cross-file (grep)."""

import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Gtk, Adw, GtkSource, Gio, GLib, GObject, Pango


class SearchBar(Gtk.Box):
    """Combined in-file search/replace + directory search bar."""

    def __init__(self, editor):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._editor = editor
        self._buffer = editor.get_buffer()
        self._search_ctx: GtkSource.SearchContext | None = None
        self._search_settings = GtkSource.SearchSettings()
        self._search_settings.set_wrap_around(True)
        self._mode = None  # None | "search" | "replace" | "dir"

        self._setup_search_context()
        self._build_ui()
        self.set_visible(False)

    def _setup_search_context(self):
        self._search_ctx = GtkSource.SearchContext(
            buffer=self._buffer,
            settings=self._search_settings,
        )
        self._search_ctx.set_highlight(True)

    def _build_ui(self):
        # ── In-file search/replace ─────────────────────────────────────────
        self._inline_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._inline_bar.set_margin_start(8)
        self._inline_bar.set_margin_end(8)
        self._inline_bar.set_margin_top(4)
        self._inline_bar.set_margin_bottom(4)

        # Search row
        search_row = Gtk.Box(spacing=4)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Find…")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_entry.connect("activate", self._on_find_next)
        search_row.append(self._search_entry)

        btn_prev = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Previous (Shift+Enter)")
        btn_prev.add_css_class("flat")
        btn_prev.connect("clicked", self._on_find_prev)
        search_row.append(btn_prev)

        btn_next = Gtk.Button(icon_name="go-down-symbolic", tooltip_text="Next (Enter)")
        btn_next.add_css_class("flat")
        btn_next.connect("clicked", self._on_find_next)
        search_row.append(btn_next)

        # Options
        self._btn_case = Gtk.ToggleButton(label="Aa", tooltip_text="Match case")
        self._btn_case.add_css_class("flat")
        self._btn_case.connect("toggled", self._on_options_changed)
        search_row.append(self._btn_case)

        self._btn_regex = Gtk.ToggleButton(label=".*", tooltip_text="Use regular expression")
        self._btn_regex.add_css_class("flat")
        self._btn_regex.connect("toggled", self._on_options_changed)
        search_row.append(self._btn_regex)

        self._match_label = Gtk.Label(label="", width_chars=8)
        self._match_label.add_css_class("dim-label")
        self._match_label.add_css_class("caption")
        search_row.append(self._match_label)

        btn_close = Gtk.Button(icon_name="window-close-symbolic")
        btn_close.add_css_class("flat")
        btn_close.connect("clicked", self._on_close)
        search_row.append(btn_close)

        self._inline_bar.append(search_row)

        # Replace row (hidden by default)
        self._replace_row = Gtk.Box(spacing=4)
        self._replace_entry = Gtk.Entry(placeholder_text="Replace with…")
        self._replace_entry.set_hexpand(True)
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
        dir_search_row.append(self._dir_entry)

        btn_dir_search = Gtk.Button(icon_name="system-search-symbolic", tooltip_text="Search")
        btn_dir_search.add_css_class("flat")
        btn_dir_search.connect("clicked", self._on_dir_search)
        dir_search_row.append(btn_dir_search)

        btn_dir_close = Gtk.Button(icon_name="window-close-symbolic")
        btn_dir_close.add_css_class("flat")
        btn_dir_close.connect("clicked", self._on_close)
        dir_search_row.append(btn_dir_close)

        self._dir_bar.append(dir_search_row)

        # Results list
        self._dir_results_scroll = Gtk.ScrolledWindow()
        self._dir_results_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._dir_results_scroll.set_max_content_height(200)
        self._dir_results_scroll.set_propagate_natural_height(True)

        self._dir_results = Gtk.ListBox()
        self._dir_results.add_css_class("boxed-list")
        self._dir_results.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._dir_results_scroll.set_child(self._dir_results)
        self._dir_bar.append(self._dir_results_scroll)

        self._dir_bar.set_visible(False)
        self.append(self._dir_bar)

        self.append(Gtk.Separator())

    # ── Public API ─────────────────────────────────────────────────────────

    def show_search(self):
        self._mode = "search"
        self._inline_bar.set_visible(True)
        self._replace_row.set_visible(False)
        self._dir_bar.set_visible(False)
        self.set_visible(True)
        self._search_entry.grab_focus()

    def show_replace(self):
        self._mode = "replace"
        self._inline_bar.set_visible(True)
        self._replace_row.set_visible(True)
        self._dir_bar.set_visible(False)
        self.set_visible(True)
        self._search_entry.grab_focus()

    def show_dir_search(self):
        self._mode = "dir"
        self._inline_bar.set_visible(False)
        self._dir_bar.set_visible(True)
        self.set_visible(True)
        self._dir_entry.grab_focus()

    # ── Signal Handlers ────────────────────────────────────────────────────

    def _on_close(self, *_):
        self.set_visible(False)
        self._mode = None
        self._search_settings.set_search_text("")
        self._match_label.set_text("")
        self._editor.grab_focus()

    def _on_options_changed(self, *_):
        self._search_settings.set_case_sensitive(self._btn_case.get_active())
        self._search_settings.set_regex_enabled(self._btn_regex.get_active())
        self._do_search()

    def _on_search_changed(self, entry):
        self._do_search()

    def _do_search(self):
        text = self._search_entry.get_text()
        self._search_settings.set_search_text(text)
        if text:
            self._update_match_count()
        else:
            self._match_label.set_text("")

    def _update_match_count(self):
        count = self._search_ctx.get_occurrences_count()
        if count < 0:
            self._match_label.set_text("…")
        elif count == 0:
            self._match_label.set_text("No results")
            self._match_label.add_css_class("error")
        else:
            self._match_label.remove_css_class("error")
            self._match_label.set_text(f"{count} found")

    def _on_find_next(self, *_):
        if not self._search_settings.get_search_text():
            return
        insert = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        found, start, end, wrapped = self._search_ctx.forward(insert)
        if found:
            self._buffer.select_range(start, end)
            self._editor.get_view().scroll_to_iter(start, 0.1, False, 0, 0)

    def _on_find_prev(self, *_):
        if not self._search_settings.get_search_text():
            return
        insert = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        found, start, end, wrapped = self._search_ctx.backward(insert)
        if found:
            self._buffer.select_range(start, end)
            self._editor.get_view().scroll_to_iter(start, 0.1, False, 0, 0)

    def _on_replace(self, *_):
        replacement = self._replace_entry.get_text()
        insert = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        found, start, end, wrapped = self._search_ctx.forward(insert)
        if found:
            self._search_ctx.replace(start, end, replacement, -1)

    def _on_replace_all(self, *_):
        replacement = self._replace_entry.get_text()
        self._search_ctx.replace_all(replacement, -1)

    def _on_dir_search(self, *_):
        query = self._dir_entry.get_text().strip()
        if not query:
            return

        # Find the root dir from the window's file explorer
        root = self._get_search_root()
        if not root:
            self._dir_results_clear()
            self._add_dir_result_label("Open a folder first to search in files.")
            return

        self._dir_results_clear()
        self._add_dir_result_label("Searching…")

        # Run grep asynchronously
        try:
            proc = Gio.Subprocess.new(
                ["grep", "-rn", "--include=*.md", "--include=*.txt", "--include=*.rst",
                 "-m", "5", query, root],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
            proc.communicate_utf8_async(None, None, self._on_grep_done, query)
        except Exception as e:
            self._dir_results_clear()
            self._add_dir_result_label(f"Search failed: {e}")

    def _on_grep_done(self, proc, result, query):
        try:
            ok, stdout, _ = proc.communicate_utf8_finish(result)
        except Exception:
            return

        self._dir_results_clear()
        if not stdout or not stdout.strip():
            self._add_dir_result_label("No results found.")
            return

        lines = stdout.strip().split("\n")
        shown = 0
        for line in lines[:100]:  # cap at 100 results
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            filepath, lineno, text = parts[0], parts[1], parts[2]
            self._add_dir_result(filepath, lineno, text.strip(), query)
            shown += 1

        if len(lines) > 100:
            self._add_dir_result_label(f"… and {len(lines) - 100} more results.")

    def _dir_results_clear(self):
        while True:
            row = self._dir_results.get_row_at_index(0)
            if row is None:
                break
            self._dir_results.remove(row)

    def _add_dir_result_label(self, text: str):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("dim-label")
        label.set_margin_start(8)
        label.set_margin_end(8)
        label.set_margin_top(4)
        label.set_margin_bottom(4)
        row.set_child(label)
        self._dir_results.append(row)

    def _add_dir_result(self, filepath: str, lineno: str, text: str, query: str):
        row = Gtk.ListBoxRow()
        row.filepath = filepath  # type: ignore[attr-defined]
        row.lineno = lineno  # type: ignore[attr-defined]

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        # File + line
        header = Gtk.Box(spacing=4)
        fname_label = Gtk.Label(
            label=f"{os.path.basename(filepath)}:{lineno}",
            xalign=0,
        )
        fname_label.add_css_class("caption")
        fname_label.add_css_class("dim-label")
        fname_label.set_ellipsize(Pango.EllipsizeMode.START)
        header.append(fname_label)
        box.append(header)

        # Matching text
        text_label = Gtk.Label(label=text[:120], xalign=0)
        text_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(text_label)

        row.set_child(box)
        self._dir_results.append(row)

        # Activate opens the file at the matching line
        def on_activate(lb, r):
            if hasattr(r, "filepath"):
                self._open_result(r.filepath, r.lineno)

        self._dir_results.connect("row-activated", on_activate)

    def _open_result(self, filepath: str, lineno: str):
        """Open a file at a specific line in the editor."""
        window = self.get_root()
        if window and hasattr(window, "file_manager"):
            window.file_manager.open_file(filepath)
            try:
                line = int(lineno) - 1
                GLib.timeout_add(100, lambda: self._goto_line_later(line))
            except ValueError:
                pass

    def _goto_line_later(self, line: int):
        self._editor.goto_line(line)
        return False

    def _get_search_root(self) -> str | None:
        window = self.get_root()
        if window and hasattr(window, "file_explorer"):
            return window.file_explorer._root_path
        return None
