"""Dialog helpers shared across the app.

Marker supports libadwaita 1.1, which lacks Adw.MessageDialog (added in 1.2),
so message dialogs fall back to Gtk.MessageDialog there. File choosers use
Gtk.FileChooserNative because Gtk.FileDialog needs GTK 4.10.
"""

import os
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from .filetypes import OPEN_DIALOG_PATTERNS

# (response id, label, appearance) — appearance is None, "suggested" or "destructive"
Response = tuple[str, str, str | None]

_HAS_ADW_MESSAGE_DIALOG = hasattr(Adw, "MessageDialog")


class MessageDialog:
    """Thin wrapper over Adw.MessageDialog / Gtk.MessageDialog."""

    def __init__(
        self,
        parent: Gtk.Window | None,
        heading: str,
        body: str,
        responses: list[Response],
        *,
        default: str | None = None,
        close_response: str = "cancel",
        on_response: Callable[[str], None] | None = None,
        extra_child: Gtk.Widget | None = None,
    ):
        self._on_response = on_response
        self._close_response = close_response
        self._ids = [rid for rid, _, _ in responses]
        self._answered = False

        if _HAS_ADW_MESSAGE_DIALOG:
            self.widget = Adw.MessageDialog(
                transient_for=parent, modal=True, heading=heading, body=body
            )
            for rid, label, appearance in responses:
                self.widget.add_response(rid, label)
                if appearance == "suggested":
                    self.widget.set_response_appearance(rid, Adw.ResponseAppearance.SUGGESTED)
                elif appearance == "destructive":
                    self.widget.set_response_appearance(rid, Adw.ResponseAppearance.DESTRUCTIVE)
            if default:
                self.widget.set_default_response(default)
            self.widget.set_close_response(close_response)
            if extra_child is not None:
                self.widget.set_extra_child(extra_child)
            self.widget.connect("response", lambda _d, rid: self._finish(rid))
        else:
            self.widget = Gtk.MessageDialog(
                transient_for=parent, modal=True, text=heading, secondary_text=body
            )
            for index, (_rid, label, appearance) in enumerate(responses):
                button = self.widget.add_button(label, index)
                if appearance == "suggested":
                    button.add_css_class("suggested-action")
                elif appearance == "destructive":
                    button.add_css_class("destructive-action")
            if default in self._ids:
                self.widget.set_default_response(self._ids.index(default))
            if extra_child is not None:
                self.widget.get_message_area().append(extra_child)
            self.widget.connect("response", self._on_gtk_response)

    def _on_gtk_response(self, dialog, response: int):
        rid = self._ids[response] if 0 <= response < len(self._ids) else self._close_response
        dialog.destroy()
        self._finish(rid)

    def _finish(self, rid: str):
        if self._answered:
            return
        self._answered = True
        if self._on_response is not None:
            self._on_response(rid)

    def present(self) -> "MessageDialog":
        self.widget.present()
        return self

    def respond(self, rid: str):
        """Answer the dialog programmatically (Enter in an extra entry, tests)."""
        if _HAS_ADW_MESSAGE_DIALOG:
            self.widget.response(rid)
        else:
            self.widget.response(self._ids.index(rid))


def ask(parent, heading, body, responses, **kwargs) -> MessageDialog:
    return MessageDialog(parent, heading, body, responses, **kwargs).present()


def show_error(parent, heading: str, body: str) -> MessageDialog:
    return ask(parent, heading, body, [("ok", "OK", None)], default="ok", close_response="ok")


def ask_unsaved_changes(parent, name: str, on_response: Callable[[str], None]) -> MessageDialog:
    """Ask Save / Discard / Cancel for one document. Calls on_response(id)."""
    return ask(
        parent,
        "Save Changes?",
        f"“{name}” has unsaved changes. Changes that are not saved will be lost.",
        [("cancel", "Cancel", None), ("discard", "Discard", "destructive"), ("save", "Save", "suggested")],
        default="save",
        on_response=on_response,
    )


# ── File choosers ──────────────────────────────────────────────────────────

_live_choosers: set = set()  # FileChooserNative must be kept alive until it answers


def _run_chooser(chooser: Gtk.FileChooserNative, on_accept: Callable[[Gtk.FileChooserNative], None],
                 on_cancel: Callable[[], None] | None = None):
    def on_response(dialog, response):
        _live_choosers.discard(dialog)
        if response == Gtk.ResponseType.ACCEPT:
            on_accept(dialog)
        elif on_cancel is not None:
            on_cancel()

    _live_choosers.add(chooser)
    chooser.connect("response", on_response)
    chooser.show()


def _set_folder(chooser: Gtk.FileChooserNative, folder: str | None):
    if folder and os.path.isdir(folder):
        try:
            chooser.set_current_folder(Gio.File.new_for_path(folder))
        except Exception:
            pass


def choose_files_to_open(parent, on_chosen: Callable[[list[str]], None], folder: str | None = None):
    chooser = Gtk.FileChooserNative(
        title="Open Files",
        transient_for=parent,
        action=Gtk.FileChooserAction.OPEN,
        accept_label="_Open",
        cancel_label="_Cancel",
        select_multiple=True,
    )
    documents = Gtk.FileFilter()
    documents.set_name("Markdown & Text")
    for pattern in OPEN_DIALOG_PATTERNS:
        documents.add_pattern(pattern)
    chooser.add_filter(documents)
    all_files = Gtk.FileFilter()
    all_files.set_name("All files")
    all_files.add_pattern("*")
    chooser.add_filter(all_files)
    _set_folder(chooser, folder)

    def accept(dialog):
        files = dialog.get_files()
        paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
        on_chosen([p for p in paths if p])

    _run_chooser(chooser, accept)


def choose_save_path(parent, on_chosen: Callable[[str | None], None],
                     name: str | None = None, folder: str | None = None):
    """Ask for a destination path. Calls on_chosen(path) or on_chosen(None) on cancel."""
    chooser = Gtk.FileChooserNative(
        title="Save As",
        transient_for=parent,
        action=Gtk.FileChooserAction.SAVE,
        accept_label="_Save",
        cancel_label="_Cancel",
    )
    _set_folder(chooser, folder)
    chooser.set_current_name(name or "Untitled.md")

    def accept(dialog):
        gfile = dialog.get_file()
        on_chosen(gfile.get_path() if gfile else None)

    _run_chooser(chooser, accept, lambda: on_chosen(None))


def choose_folder(parent, on_chosen: Callable[[str], None]):
    chooser = Gtk.FileChooserNative(
        title="Open Folder",
        transient_for=parent,
        action=Gtk.FileChooserAction.SELECT_FOLDER,
        accept_label="_Open",
        cancel_label="_Cancel",
    )

    def accept(dialog):
        gfile = dialog.get_file()
        if gfile and gfile.get_path():
            on_chosen(gfile.get_path())

    _run_chooser(chooser, accept)
