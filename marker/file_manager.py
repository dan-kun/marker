"""File open/save/new operations and dirty state tracking."""

import os
from typing import Callable
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, GObject


MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mkd", ".mdown"}
TEXT_EXTENSIONS = {".txt", ".rst", ".log", ".csv", ".json", ".yaml", ".yml",
                   ".toml", ".ini", ".cfg", ".conf", ".sh", ".py", ".js"}


class FileManager(GObject.Object):
    """Manages file I/O and dirty state for the editor."""

    __gsignals__ = {
        "file-changed": (GObject.SignalFlags.RUN_LAST, None, (str, bool)),
    }

    def __init__(self, window, recents_manager=None):
        super().__init__()
        self._window = window
        self._editor = window.editor
        self._recents = recents_manager
        self._current_path: str | None = None
        self._is_modified = False

        self._editor.connect("content-changed", self._on_content_changed)

    # ── State ──────────────────────────────────────────────────────────────

    @property
    def current_path(self) -> str | None:
        return self._current_path

    @property
    def is_modified(self) -> bool:
        return self._is_modified

    def _set_path(self, path: str | None):
        self._current_path = path
        self._is_modified = False
        self.emit("file-changed", path or "", False)
        self._update_language(path)

    def _set_modified(self, modified: bool):
        if modified != self._is_modified:
            self._is_modified = modified
            self.emit("file-changed", self._current_path or "", modified)

    def _on_content_changed(self, editor, text):
        self._set_modified(True)

    def _update_language(self, path: str | None):
        if not path:
            self._editor.set_language("markdown")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in MARKDOWN_EXTENSIONS:
            self._editor.set_language("markdown")
        else:
            self._editor.set_language(None)

    # ── Operations ─────────────────────────────────────────────────────────

    def new_file(self):
        self._with_discard_check(self._do_new_file)

    def _do_new_file(self):
        self._editor.set_text("")
        self._set_path(None)
        self._editor.grab_focus()

    def open_file(self, path: str):
        self._with_discard_check(lambda: self._do_open_file(path))

    def _do_open_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            self._show_error("Cannot open file", str(e))
            return
        self._editor.set_text(text)
        self._set_path(path)
        self._editor.grab_focus()

        if self._recents:
            self._recents.push(path)

        # Tell explorer to highlight folder
        explorer = self._window.file_explorer
        folder = os.path.dirname(path)
        explorer.set_root(folder)

    def open_file_dialog(self):
        self._with_discard_check(self._show_open_dialog)

    def _show_open_dialog(self):
        filter_md = Gtk.FileFilter()
        filter_md.set_name("Markdown & Text")
        for pat in ("*.md", "*.markdown", "*.txt", "*.rst"):
            filter_md.add_pattern(pat)

        dialog = Gtk.FileChooserNative(
            title="Open File",
            transient_for=self._window,
            action=Gtk.FileChooserAction.OPEN,
            accept_label="_Open",
            cancel_label="_Cancel",
        )
        dialog.add_filter(filter_md)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All files")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        dialog.connect("response", self._on_open_dialog_done)
        dialog.show()
        self._open_dialog = dialog  # keep reference

    def _on_open_dialog_done(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = dialog.get_file()
            if gfile:
                self._do_open_file(gfile.get_path())
        self._open_dialog = None

    def save_file(self):
        if self._current_path:
            self._write_file(self._current_path)
        else:
            self.save_file_as()

    def save_file_as(self):
        dialog = Gtk.FileChooserNative(
            title="Save File As",
            transient_for=self._window,
            action=Gtk.FileChooserAction.SAVE,
            accept_label="_Save",
            cancel_label="_Cancel",
        )
        if self._current_path:
            import os
            dialog.set_current_name(os.path.basename(self._current_path))
        dialog.connect("response", self._on_save_dialog_done)
        dialog.show()
        self._save_dialog = dialog  # keep reference

    def _on_save_dialog_done(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = dialog.get_file()
            if gfile:
                self._write_file(gfile.get_path())
        self._save_dialog = None

    def _write_file(self, path: str):
        text = self._editor.get_text()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            self._show_error("Cannot save file", str(e))
            return
        self._set_path(path)
        if self._recents:
            self._recents.push(path)

    def close_file(self):
        self._with_discard_check(self._do_new_file)

    # ── Unsaved changes dialog (async) ─────────────────────────────────────

    def _with_discard_check(self, callback: Callable):
        """Run callback, asking the user first if there are unsaved changes."""
        if not self._is_modified:
            callback()
            return

        dialog = Adw.MessageDialog(
            transient_for=self._window,
            heading="Unsaved Changes",
            body="Do you want to save your changes before continuing?",
        )
        dialog.add_response("discard", "Discard")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response):
            if response == "save":
                self.save_file()
                callback()
            elif response == "discard":
                self._is_modified = False
                callback()
            # "cancel" → do nothing

        dialog.connect("response", on_response)
        dialog.present()

    def _show_error(self, title: str, message: str):
        dialog = Adw.MessageDialog(
            transient_for=self._window,
            heading=title,
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.present()
