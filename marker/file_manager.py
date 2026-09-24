"""Loading, saving and dirty-state tracking for one editor tab."""

import os
import time
from collections.abc import Callable

from gi.repository import GObject

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

        self._autosave = Debouncer(30_000, self._on_autosave)
        self._handlers = [
            self._buffer.connect("modified-changed", self._on_modified_changed),
            self._buffer.connect("changed", self._on_buffer_changed),
        ]

    def dispose(self):
        self._autosave.cancel()
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
    def is_blank(self) -> bool:
        """Untitled, empty and unmodified: safe to reuse for another file."""
        return self._current_path is None and self._editor.is_empty() and not self.is_modified

    def _set_path(self, path: str | None):
        self._current_path = path
        self._editor.set_language("markdown" if path is None or is_markdown(path) else None)
        self._buffer.set_modified(False)
        self.emit("file-changed", path or "", False)

    def _on_modified_changed(self, buf):
        self.emit("file-changed", self._current_path or "", buf.get_modified())

    # ── Loading ────────────────────────────────────────────────────────────

    def new_file(self):
        self.confirm_discard(lambda ok: ok and self._reset())

    def _reset(self):
        self._editor.set_text("")
        self._autosave.cancel()
        self._encoding, self._newline = "utf-8", "\n"
        self._mtime_ns = self._last_saved = None
        self._set_path(None)
        self._editor.grab_focus()

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

        self._editor.set_text(text_file.text)
        self._autosave.cancel()  # set_text() counts as an edit
        self._encoding = text_file.encoding
        self._newline = text_file.newline
        self._mtime_ns = text_file.mtime_ns
        self._last_saved = None
        self._set_path(path)

        if self._recents:
            self._recents.push(path)
        self.emit("loaded", path)
        return True

    def reload(self, on_done: DoneCallback = None):
        path = self._current_path
        if path:
            self.confirm_discard(lambda ok: _finish(on_done, ok and self.load(path)))

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

    def _do_write(self, path: str, on_done: DoneCallback, encoding: str | None = None) -> bool:
        encoding = encoding or self._encoding
        try:
            mtime_ns = write_text_file(path, self._editor.get_text(), encoding, self._newline)
        except UnicodeEncodeError:
            self._ask_utf8(path, on_done)
            return False
        except OSError as e:
            dialogs.show_error(self._window, "Cannot Save File", e.strerror or str(e))
            _finish(on_done, False)
            return False

        self._autosave.cancel()
        self._encoding = encoding
        self._mtime_ns = mtime_ns
        self._last_saved = time.time()
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
        if not path or not self.is_modified or self._changed_on_disk(path):
            return  # never overwrite someone else's changes without asking
        self._do_write(path, None)

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
