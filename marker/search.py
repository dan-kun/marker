"""Search bar: in-file (GtkSourceSearchContext) and cross-file (grep)."""

import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")

from gi.repository import Gdk, Gio, GLib, GObject, Gtk, GtkSource, Pango

from .filetypes import SHOWN_EXTENSIONS
from .titles import display, short_labels

MAX_DIR_RESULTS = 200
MAX_MATCHES_PER_FILE = 5


def _any_case(extension: str) -> str:
    """A glob that matches extension in any letter case: ".md" → ".[mM][dD]"."""
    return "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else c for c in extension)


def grep_argv(query: str, match_case: bool = False) -> list[str]:
    """grep command for a literal search of the current directory.

    -F: literal text; -e/--: the query can never be read as an option;
    -I: skip binary files; -Z: NUL after the file name.
    grep applies --exclude-dir to the directory named on the command line
    too, so we search "." from inside the folder with a pattern that skips
    hidden subfolders (.git) but not "." itself. Passing the folder's path
    with --exclude-dir=.* would skip a hidden root such as ~/.notes entirely.
    """
    argv = ["grep", "-rnIFZ", "-m", str(MAX_MATCHES_PER_FILE), "--exclude-dir=.[!.]*"]
    if not match_case:
        argv.append("-i")
    # README.MD is listed in the sidebar, so it has to be searched as well
    argv += [f"--include=*{_any_case(ext)}" for ext in sorted(SHOWN_EXTENSIONS)]
    return argv + ["-e", query, "--", "."]


def search_roots(folders: list[str]) -> list[str]:
    """The folders to run grep in: existing ones, without any folder that
    lies inside another (its files would be reported twice)."""
    folders = [os.path.abspath(f) for f in dict.fromkeys(folders) if os.path.isdir(f)]
    return [
        folder for folder in folders
        if not any(other != folder and os.path.commonpath([folder, other]) == other
                   for other in folders)
    ]


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


class ResultRow(Gtk.ListBoxRow):
    """One "Find in Folder" match: where it is and the matching line."""

    def __init__(self, path: str, lineno: int, text: str, root: str, root_label: str | None = None):
        """root_label names the folder when several are searched at once."""
        super().__init__()
        self.location = (path, lineno)  # lineno is 1-based, as grep reports it
        self.set_tooltip_text(display(path))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        relative = os.path.relpath(path, root)
        if root_label:
            relative = os.path.join(root_label, relative)
        where = Gtk.Label(label=f"{display(relative)}:{lineno}", xalign=0)
        where.add_css_class("caption")
        where.add_css_class("marker-dim")
        where.set_ellipsize(Pango.EllipsizeMode.START)
        box.append(where)

        text_label = Gtk.Label(label=text[:200], xalign=0)
        text_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(text_label)

        self.set_child(box)


class SearchBar(Gtk.Box):
    """Combined in-file search/replace + directory search bar."""

    __gsignals__ = {
        # (path, 0-based line) of a "Find in Folder" result the user picked
        "open-location": (GObject.SignalFlags.RUN_LAST, None, (object, int)),
    }

    def __init__(self, editor, roots_provider: Callable[[], list[str]]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._roots_provider = roots_provider
        self._search_settings = GtkSource.SearchSettings()
        self._search_settings.set_wrap_around(True)
        self._grep_cancellable: Gio.Cancellable | None = None
        self._grep_processes: list[Gio.Subprocess] = []

        self._editor = editor
        self._buffer = editor.get_buffer()
        self._search_ctx, self._count_handler = self._new_context()
        self._search_ctx.set_highlight(False)

        self._build_ui()
        self.set_visible(False)

    def _build_ui(self):
        # ── In-file search/replace ─────────────────────────────────────────
        self._inline_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._inline_bar.set_margin_start(8)
        self._inline_bar.set_margin_end(8)
        self._inline_bar.set_margin_top(4)
        self._inline_bar.set_margin_bottom(4)

        # Both entries share a column so that they line up
        grid = Gtk.Grid(column_spacing=4, row_spacing=2)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Find…")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", lambda *_: self._do_search())
        self._search_entry.connect("activate", self._on_find_next)
        self._search_entry.connect("next-match", self._on_find_next)
        self._search_entry.connect("previous-match", self._on_find_prev)
        self._search_entry.connect("stop-search", self._on_close)
        self._add_shift_enter(self._search_entry, self._on_find_prev)
        grid.attach(self._search_entry, 0, 0, 1, 1)

        search_buttons = Gtk.Box(spacing=4)

        btn_prev = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Previous (Shift+Enter)")
        btn_prev.add_css_class("flat")
        btn_prev.connect("clicked", self._on_find_prev)
        search_buttons.append(btn_prev)

        btn_next = Gtk.Button(icon_name="go-down-symbolic", tooltip_text="Next (Enter)")
        btn_next.add_css_class("flat")
        btn_next.connect("clicked", self._on_find_next)
        search_buttons.append(btn_next)

        self._btn_case = Gtk.ToggleButton(label="Aa", tooltip_text="Match case")
        self._btn_case.add_css_class("flat")
        self._btn_case.connect("toggled", self._on_options_changed)
        search_buttons.append(self._btn_case)

        self._btn_regex = Gtk.ToggleButton(label=".*", tooltip_text="Use regular expression")
        self._btn_regex.add_css_class("flat")
        self._btn_regex.connect("toggled", self._on_options_changed)
        search_buttons.append(self._btn_regex)

        self._match_label = Gtk.Label(label="", width_chars=10, hexpand=True, xalign=0)
        self._match_label.add_css_class("marker-dim")
        self._match_label.add_css_class("caption")
        search_buttons.append(self._match_label)

        btn_close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Close (Esc)")
        btn_close.add_css_class("flat")
        btn_close.connect("clicked", self._on_close)
        search_buttons.append(btn_close)

        grid.attach(search_buttons, 1, 0, 1, 1)

        # Replace row (hidden by default)
        self._replace_entry = Gtk.Entry(placeholder_text="Replace with…")
        self._replace_entry.set_hexpand(True)
        self._replace_entry.connect("activate", self._on_replace)
        self._add_escape(self._replace_entry)
        grid.attach(self._replace_entry, 0, 1, 1, 1)

        replace_buttons = Gtk.Box(spacing=4)
        btn_replace = Gtk.Button(label="Replace", tooltip_text="Replace this match (Enter)")
        btn_replace.add_css_class("flat")
        btn_replace.connect("clicked", self._on_replace)
        replace_buttons.append(btn_replace)

        btn_replace_all = Gtk.Button(label="Replace All")
        btn_replace_all.add_css_class("flat")
        btn_replace_all.connect("clicked", self._on_replace_all)
        replace_buttons.append(btn_replace_all)
        grid.attach(replace_buttons, 1, 1, 1, 1)

        self._replace_widgets = (self._replace_entry, replace_buttons)
        self._show_replace_row(False)
        self._inline_bar.append(grid)
        self.append(self._inline_bar)

        # ── Directory search ───────────────────────────────────────────────
        self._dir_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._dir_bar.set_margin_start(8)
        self._dir_bar.set_margin_end(8)
        self._dir_bar.set_margin_top(4)
        self._dir_bar.set_margin_bottom(4)

        dir_search_row = Gtk.Box(spacing=4)

        self._dir_entry = Gtk.SearchEntry(placeholder_text="Search in the sidebar's folders…")
        self._dir_entry.set_hexpand(True)
        self._dir_entry.connect("activate", self._on_dir_search)
        self._dir_entry.connect("stop-search", self._on_close)
        dir_search_row.append(self._dir_entry)

        self._btn_dir_case = Gtk.ToggleButton(label="Aa", tooltip_text="Match case")
        self._btn_dir_case.add_css_class("flat")
        dir_search_row.append(self._btn_dir_case)

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
        self._search_ctx.disconnect(self._count_handler)
        self._search_ctx.set_highlight(False)
        self._editor = editor
        self._buffer = editor.get_buffer()
        self._search_ctx, self._count_handler = self._new_context()
        self._update_match_count()

    def _new_context(self) -> tuple[GtkSource.SearchContext, int]:
        """A search context on the current buffer and its count handler."""
        context = GtkSource.SearchContext(buffer=self._buffer, settings=self._search_settings)
        context.set_highlight(self.get_visible())
        # The count is computed asynchronously; -1 until the scan finishes.
        handler = context.connect("notify::occurrences-count", lambda *_: self._update_match_count())
        return context, handler

    def _show_replace_row(self, visible: bool):
        for widget in self._replace_widgets:
            widget.set_visible(visible)

    def show_search(self):
        self._show_inline(replace=False)

    def show_replace(self):
        self._show_inline(replace=True)

    def _show_inline(self, replace: bool):
        self._inline_bar.set_visible(True)
        self._show_replace_row(replace)
        self._dir_bar.set_visible(False)
        self.set_visible(True)
        self._search_ctx.set_highlight(True)

        # Seed the query with a single-line selection, like most editors
        selection = self._editor.get_selection()
        if selection:
            selected = self._buffer.get_text(*selection, True)
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
        self._stop_grep()
        self._editor.grab_focus()

    def _stop_grep(self):
        """Abandon a folder search that is still running. Cancelling alone
        only stops us listening: grep would carry on reading the disk."""
        if self._grep_cancellable is not None:
            self._grep_cancellable.cancel()
            self._grep_cancellable = None
        for process in self._grep_processes:
            process.force_exit()
        self._grep_processes = []

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
        selection = self._editor.get_selection()
        if selection:
            return selection[1] if forward else selection[0]
        return self._buffer.get_iter_at_mark(self._buffer.get_insert())

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
        found, start, end, _ = self._search_ctx.forward(self._search_origin(forward=False))
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

        roots = search_roots(self._roots_provider())
        self._stop_grep()
        self._dir_results_clear()
        if not roots:
            self._add_dir_result_label("Add a folder to the sidebar to search in files.")
            return

        self._grep_cancellable = cancellable = Gio.Cancellable()
        argv = grep_argv(query, match_case=self._btn_dir_case.get_active())
        self._add_dir_result_label("Searching…")

        # One grep per folder, run side by side; results are shown together
        # once the last one finishes.
        labels = short_labels(roots) if len(roots) > 1 else {}
        search = {"pending": len(roots), "results": [], "total": 0, "errors": []}
        for root in roots:
            try:
                launcher = Gio.SubprocessLauncher.new(
                    Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
                )
                launcher.set_cwd(root)
                proc = launcher.spawnv(argv)
            except GLib.Error as e:
                search["errors"].append(e.message)
                self._on_grep_finished(search, cancellable)
                continue
            self._grep_processes.append(proc)
            proc.communicate_async(
                None, cancellable, self._on_grep_done, (search, cancellable, root, labels.get(root))
            )

    def _on_grep_done(self, proc, result, data):
        search, cancellable, root, label = data
        if proc in self._grep_processes:
            self._grep_processes.remove(proc)
        try:
            _, stdout, _ = proc.communicate_finish(result)
        except GLib.Error as e:
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                return  # a newer search took over
            search["errors"].append(e.message)
        else:
            # grep exits with 1 for "no match" and 2 for errors such as unreadable files
            if proc.get_exit_status() == 2 and not stdout:
                search["errors"].append(f"grep could not read {root}")
            results, total = parse_grep_output(stdout.get_data() if stdout else b"")
            search["total"] += total
            # grep ran inside root, so paths look like "./sub/file.md"
            search["results"] += [
                (os.path.normpath(os.path.join(root, path)), lineno, text, root, label)
                for path, lineno, text in results
            ]
        self._on_grep_finished(search, cancellable)

    def _on_grep_finished(self, search: dict, cancellable: Gio.Cancellable):
        search["pending"] -= 1
        if search["pending"] > 0 or cancellable.is_cancelled():
            return
        self._dir_results_clear()
        results = sorted(search["results"])[:MAX_DIR_RESULTS]
        for path, lineno, text, root, label in results:
            self._dir_results.append(ResultRow(path, lineno, text, root, label))
        if search["total"] > len(results):
            self._add_dir_result_label(f"… and {search['total'] - len(results)} more results.")
        for error in search["errors"]:
            self._add_dir_result_label(f"Search failed: {error}")
        if not results and not search["errors"]:
            self._add_dir_result_label("No results found.")

    def _dir_results_clear(self):
        while (row := self._dir_results.get_row_at_index(0)) is not None:
            self._dir_results.remove(row)

    def _add_dir_result_label(self, text: str):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("marker-dim")
        label.set_margin_start(8)
        label.set_margin_end(8)
        label.set_margin_top(4)
        label.set_margin_bottom(4)
        row.set_child(label)
        self._dir_results.append(row)

    def _on_dir_result_activated(self, listbox, row):
        if isinstance(row, ResultRow):
            path, lineno = row.location
            self.emit("open-location", path, lineno - 1)
