"""Loading, saving and dirty-state tracking for one editor tab."""

import os
import time
from collections.abc import Callable

from gi.repository import Gio, GObject

from . import dialogs
from .filetypes import is_markdown
from .textio import (
    ENCODING_NAMES,
    NEWLINE_NAMES,
    BinaryFileError,
    read_text_file,
    write_text_file,
)
from .utils import Debouncer

# Called with True when the operation completed, False if cancelled or failed.
DoneCallback = Callable[[bool], None] | None


def _finish(on_done: DoneCallback, ok: bool):
    if on_done is not None:
        on_done(ok)


class FileManager(GObject.Object):
    """Owns the file behind one editor: path, encoding, line endings, dirty state."""

    __gsignals__ = {
        # (path or "", is_modified) — whenever either changes
        "file-changed": (GObject.SignalFlags.RUN_LAST, None, (str, bool)),
        "loaded": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "saved": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, window, editor, recents_manager=None, settings=None):
        super().__init__()
        self._window = window
        self._editor = editor
        self._buffer = editor.get_buffer()
        self._recents = recents_manager
        self._settings = settings

        self._current_path: str | None = None
        self._encoding = "utf-8"
        self._newline = "\n"
        self._mtime_ns: int | None = None
        self._last_saved: float | None = None

        # Set when another program changed the file while it has unsaved edits here
        self._disk_conflict = False
        # Why the last auto-save did not happen, or None
        self._autosave_problem: str | None = None
        self._monitor: Gio.FileMonitor | None = None
        self._monitored_path: str | None = None
        self._disk_check = Debouncer(300, self._check_disk)

        self._autosave = Debouncer(30_000, self._on_autosave)
        self._handlers = [
            self._buffer.connect("modified-changed", self._on_modified_changed),
            self._buffer.connect("changed", self._on_buffer_changed),
        ]

    def dispose(self):
        self._autosave.cancel()
        self._watch(None)
        for handler in self._handlers:
            self._buffer.disconnect(handler)
        self._handlers = []

    # ── State ──────────────────────────────────────────────────────────────

    @property
    def current_path(self) -> str | None:
        return self._current_path

    @property
    def is_modified(self) -> bool:
        return self._buffer.get_modified()

    @property
    def display_name(self) -> str:
        return os.path.basename(self._current_path) if self._current_path else "Untitled"

    @property
    def encoding_label(self) -> str:
        return ENCODING_NAMES.get(self._encoding, self._encoding.upper())

    @property
    def newline_label(self) -> str:
        return NEWLINE_NAMES[self._newline]

    @property
    def last_saved(self) -> float | None:
        """Time of the last save in this session, or None."""
        return self._last_saved

    @property
    def changed_on_disk(self) -> bool:
        """Another program changed the file and the editor has unsaved edits."""
        return self._disk_conflict

    @property
    def autosave_problem(self) -> str | None:
        return self._autosave_problem

    @property
    def is_blank(self) -> bool:
        """Untitled, empty and unmodified: safe to reuse for another file."""
        return self._current_path is None and self._editor.is_empty() and not self.is_modified

    def _set_path(self, path: str | None):
        self._current_path = path
        self._editor.set_language("markdown" if path is None or is_markdown(path) else None)
        self._buffer.set_modified(False)
        self._watch(path)
        self.emit("file-changed", path or "", False)

    def _on_modified_changed(self, buf):
        self.emit("file-changed", self._current_path or "", buf.get_modified())

    # ── Loading ────────────────────────────────────────────────────────────

    def new_file(self):
        def proceed(ok: bool):
            if ok:
                self._reset()

        self.confirm_discard(proceed)

    def _reset(self):
        self._editor.set_text("")
        self._autosave.cancel()
        self._encoding, self._newline = "utf-8", "\n"
        self._mtime_ns = self._last_saved = None
        self._disk_conflict, self._autosave_problem = False, None
        self._set_path(None)
        self._editor.grab_focus()

    def start_new(self, path: str):
        """Start an empty document that will be created at path on first save."""
        self._reset()
        self._set_path(path)

    def load(self, path: str) -> bool:
        """Replace the buffer with the file at path. Shows an error on failure."""
        try:
            text_file = read_text_file(path)
        except BinaryFileError:
            dialogs.show_error(self._window, "Cannot Open File",
                               f"“{os.path.basename(path)}” is not a text file.")
            return False
        except OSError as e:
            dialogs.show_error(self._window, "Cannot Open File", e.strerror or str(e))
            return False

        self._show(path, text_file)
        self._last_saved = None
        if self._recents:
            self._recents.push(path)
        self.emit("loaded", path)
        return True

    def _show(self, path: str, text_file):
        self._editor.set_text(text_file.text)
        self._autosave.cancel()  # set_text() counts as an edit
        self._encoding = text_file.encoding
        self._newline = text_file.newline
        self._mtime_ns = text_file.mtime_ns
        self._disk_conflict, self._autosave_problem = False, None
        self._set_path(path)

    def reload(self, on_done: DoneCallback = None, discard: bool = False):
        """Re-read the file from disk. Asks about unsaved edits unless discard is set."""
        path = self._current_path
        if not path:
            return
        if discard:
            _finish(on_done, self.load(path))
        else:
            self.confirm_discard(lambda ok: _finish(on_done, ok and self.load(path)))

    # ── Changes made by other programs ─────────────────────────────────────

    def _watch(self, path: str | None):
        if path == self._monitored_path:
            return
        if self._monitor is not None:
            self._monitor.cancel()
        self._monitor, self._monitored_path = None, path
        self._disk_check.cancel()
        if path is None:
            return
        try:
            self._monitor = Gio.File.new_for_path(path).monitor_file(Gio.FileMonitorFlags.NONE, None)
        except Exception:
            return  # no monitoring on this filesystem: saving still checks
        self._monitor.connect("changed", lambda *_: self._disk_check.trigger())

    def _check_disk(self):
        """React to a change on disk: follow it when the editor has no unsaved
        edits, otherwise flag the conflict and let the user decide."""
        path = self._current_path
        if not path or not self._changed_on_disk(path):
            return  # our own save, or a touch that changed nothing we track
        if self.is_modified:
            if not self._disk_conflict:
                self._disk_conflict = True
                self.emit("file-changed", path, True)
            return
        try:
            text_file = read_text_file(path)
        except (OSError, BinaryFileError):
            return
        if text_file.text == self._editor.get_text():
            self._mtime_ns = text_file.mtime_ns
            return
        line, column = self._editor.get_cursor_position()
        self._show(path, text_file)
        self._editor.set_cursor_position(line, column)

    def dismiss_disk_change(self):
        """Hide the conflict notice. Saving still asks before overwriting."""
        if self._disk_conflict:
            self._disk_conflict = False
            self.emit("file-changed", self._current_path or "", self.is_modified)

    # ── Saving ─────────────────────────────────────────────────────────────

    def save_file(self, on_done: DoneCallback = None):
        if self._current_path:
            self._write_file(self._current_path, on_done)
        else:
            self.save_file_as(on_done)

    def save_file_as(self, on_done: DoneCallback = None):
        folder = os.path.dirname(self._current_path) if self._current_path else None
        name = self.display_name if self._current_path else "Untitled.md"

        def chosen(path):
            if path:
                self._write_file(path, on_done)
            else:
                _finish(on_done, False)

        dialogs.choose_save_path(self._window, chosen, name=name, folder=folder)

    def _changed_on_disk(self, path: str) -> bool:
        if path != self._current_path or self._mtime_ns is None:
            return False
        try:
            return os.stat(path).st_mtime_ns != self._mtime_ns
        except OSError:
            return False  # deleted or unreadable: saving recreates it

    def _write_file(self, path: str, on_done: DoneCallback):
        if not self._changed_on_disk(path):
            self._do_write(path, on_done)
            return

        def on_response(rid):
            if rid == "overwrite":
                self._do_write(path, on_done)
            else:
                _finish(on_done, False)

        dialogs.ask(
            self._window,
            "File Changed on Disk",
            f"“{os.path.basename(path)}” was modified by another program after it was "
            "opened. Saving will replace those changes.",
            [("cancel", "Cancel", None), ("overwrite", "Overwrite", "destructive")],
            default="cancel",
            on_response=on_response,
        )

    def _do_write(self, path: str, on_done: DoneCallback, encoding: str | None = None,
                  quiet: bool = False) -> bool:
        """Write the buffer to path. quiet (auto-save) records a failure in
        autosave_problem instead of interrupting with a dialog."""
        encoding = encoding or self._encoding
        try:
            mtime_ns = write_text_file(path, self._editor.get_text(), encoding, self._newline)
        except UnicodeEncodeError:
            if quiet:
                self._set_autosave_problem(f"some characters cannot be saved as {self.encoding_label}")
            else:
                self._ask_utf8(path, on_done)
            return False
        except OSError as e:
            if quiet:
                self._set_autosave_problem(e.strerror or str(e))
            else:
                dialogs.show_error(self._window, "Cannot Save File", e.strerror or str(e))
            _finish(on_done, False)
            return False

        self._autosave.cancel()
        self._encoding = encoding
        self._mtime_ns = mtime_ns
        self._last_saved = time.time()
        self._disk_conflict, self._autosave_problem = False, None
        self._set_path(path)
        if self._recents:
            self._recents.push(path)
        self.emit("saved", path)
        _finish(on_done, True)
        return True

    def _ask_utf8(self, path: str, on_done: DoneCallback):
        def on_response(rid):
            if rid == "utf8":
                self._do_write(path, on_done, encoding="utf-8")
            else:
                _finish(on_done, False)

        dialogs.ask(
            self._window,
            "Change Encoding?",
            f"The document contains characters that cannot be saved as {self.encoding_label}.",
            [("cancel", "Cancel", None), ("utf8", "Save as UTF-8", "suggested")],
            default="utf8",
            on_response=on_response,
        )

    # ── Auto-save ──────────────────────────────────────────────────────────

    def _on_buffer_changed(self, buf):
        settings = self._settings
        if settings is None or not settings["auto-save"] or not self._current_path:
            return
        self._autosave.delay_ms = settings["auto-save-delay"] * 1000
        self._autosave.trigger()

    def _on_autosave(self):
        path = self._current_path
        if not path or not self.is_modified:
            return
        if self._changed_on_disk(path):
            # Never overwrite someone else's changes without asking
            self._set_autosave_problem("the file changed on disk")
            self._check_disk()
            return
        self._do_write(path, None, quiet=True)

    def _set_autosave_problem(self, problem: str | None):
        if problem != self._autosave_problem:
            self._autosave_problem = problem
            self.emit("file-changed", self._current_path or "", self.is_modified)

    # ── Unsaved changes ────────────────────────────────────────────────────

    def confirm_discard(self, on_done: Callable[[bool], None]):
        """Call on_done(True) when it is safe to drop the buffer's contents.

        With unsaved changes, asks Save / Discard / Cancel first. "Save" only
        proceeds once the file has actually been written.
        """
        if not self.is_modified:
            on_done(True)
            return

        def on_response(rid):
            if rid == "save":
                self.save_file(on_done)
            else:
                on_done(rid == "discard")

        dialogs.ask_unsaved_changes(self._window, self.display_name, on_response)
