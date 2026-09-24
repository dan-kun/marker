"""Saving, closing and dirty-state behaviour, driven through the real window."""

import os

from conftest import iterate, needs_display, wait_for

pytestmark = needs_display


def type_text(editor, text):
    buf = editor.get_buffer()
    buf.begin_user_action()
    buf.insert(buf.get_end_iter(), text)
    buf.end_user_action()


def test_save_on_new_file_waits_for_the_chooser(window, save_as, dialogs_log, tmp_path):
    """C1: "Save" in the unsaved-changes dialog must not clear the buffer
    before the user has picked a destination and the file was written."""
    tab = window.tab_manager.active_tab
    type_text(tab.editor, "precious text")
    save_as.defer = True

    tab.file_manager.new_file()
    dialogs_log[-1].respond("save")
    assert tab.editor.get_text() == "precious text"  # still waiting for the chooser

    target = tmp_path / "kept.md"
    save_as.answer(str(target))
    assert target.read_text() == "precious text"
    assert tab.editor.get_text() == ""  # now the new document replaces it


def test_cancelled_save_keeps_the_document(window, save_as, dialogs_log):
    tab = window.tab_manager.active_tab
    type_text(tab.editor, "draft")
    save_as.path = None  # user cancels the chooser

    tab.file_manager.new_file()
    dialogs_log[-1].respond("save")
    assert tab.editor.get_text() == "draft"
    assert tab.file_manager.is_modified


def test_failed_save_keeps_the_document(window, save_as, dialogs_log, tmp_path):
    tab = window.tab_manager.active_tab
    type_text(tab.editor, "draft")
    save_as.path = str(tmp_path / "missing-dir" / "x.md")

    tab.file_manager.new_file()
    dialogs_log[-1].respond("save")
    assert dialogs_log[-1].widget.get_heading() == "Cannot Save File"
    assert tab.editor.get_text() == "draft"


def test_window_close_asks_and_can_be_cancelled(window, dialogs_log):
    """C2: closing with unsaved changes must ask first."""
    type_text(window.editor, "unsaved")
    assert window.emit("close-request") is True  # blocked
    dialogs_log[-1].respond("cancel")
    iterate(0.1)
    assert window.get_visible()
    assert window.editor.get_text() == "unsaved"


def test_window_close_with_several_documents_offers_save_all(window, dialogs_log, tmp_path):
    paths = []
    for name in ("a.md", "b.md"):
        path = tmp_path / name
        path.write_text("")
        paths.append(path)
        tab = window.open_file(str(path))
        type_text(tab.editor, f"content of {name}")

    assert window.emit("close-request") is True
    dialog = dialogs_log[-1]
    assert "2 documents" in dialog.widget.get_body()
    dialog.respond("save")
    iterate(0.1)
    assert [p.read_text() for p in paths] == ["content of a.md", "content of b.md"]
    assert not window.get_visible()


def test_closing_a_modified_tab_waits_for_the_answer(window, dialogs_log, tmp_path):
    first = window.tab_manager.active_tab
    second = window.tab_manager.new_tab()
    type_text(second.editor, "unsaved")

    window.tab_manager.close_active_tab()
    iterate(0.1)
    assert len(window.tab_manager.tabs()) == 2  # still open while the dialog is up
    dialogs_log[-1].respond("cancel")
    iterate(0.1)
    assert len(window.tab_manager.tabs()) == 2

    window.tab_manager.close_active_tab()
    dialogs_log[-1].respond("discard")
    iterate(0.1)
    assert window.tab_manager.tabs() == [first]


def test_undo_back_to_saved_state_clears_modified(window, tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("hello")
    tab = window.open_file(str(path))
    type_text(tab.editor, " world")
    assert tab.file_manager.is_modified
    tab.editor.undo()
    assert not tab.file_manager.is_modified
    assert tab.page.get_indicator_icon() is None


def test_status_bar_reports_saves_not_opens(window, tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("hello")
    tab = window.open_file(str(path))
    assert window._status_save.get_text() == ""
    type_text(tab.editor, "!")
    assert window._status_save.get_text() == "Modified"
    tab.file_manager.save_file()
    assert window._status_save.get_text() == "Saved just now"


def test_external_change_is_not_overwritten_silently(window, dialogs_log, tmp_path):
    path = tmp_path / "shared.md"
    path.write_text("v1")
    tab = window.open_file(str(path))
    type_text(tab.editor, " mine")
    stat = os.stat(path)
    path.write_text("theirs")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))

    tab.file_manager.save_file()
    assert dialogs_log[-1].widget.get_heading() == "File Changed on Disk"
    dialogs_log[-1].respond("cancel")
    assert path.read_text() == "theirs"

    tab.file_manager.save_file()
    dialogs_log[-1].respond("overwrite")
    assert path.read_text() == "v1 mine"


def test_encoding_and_line_endings_survive_editing(window, tmp_path):
    path = tmp_path / "legacy.txt"
    path.write_bytes("línea uno\r\n".encode("cp1252"))
    tab = window.open_file(str(path))
    assert window._status_encoding.get_text() == "Windows-1252 · CRLF"
    type_text(tab.editor, "línea dos\n")
    tab.file_manager.save_file()
    assert path.read_bytes() == "línea uno\r\nlínea dos\r\n".encode("cp1252")


def test_unencodable_text_asks_before_switching_to_utf8(window, dialogs_log, tmp_path):
    path = tmp_path / "legacy.txt"
    path.write_bytes("café".encode("cp1252"))
    tab = window.open_file(str(path))
    type_text(tab.editor, " 🙂")
    tab.file_manager.save_file()
    assert dialogs_log[-1].widget.get_heading() == "Change Encoding?"
    dialogs_log[-1].respond("utf8")
    assert path.read_text(encoding="utf-8") == "café 🙂"


def test_binary_files_are_refused(window, dialogs_log, tmp_path):
    path = tmp_path / "blob.md"
    path.write_bytes(b"\x00\x01\x02")
    assert window.open_file(str(path)) is None
    assert dialogs_log[-1].widget.get_heading() == "Cannot Open File"
    assert len(window.tab_manager.tabs()) == 1


def test_autosave_writes_named_files(window, tmp_path):
    path = tmp_path / "auto.md"
    path.write_text("a")
    window.settings["auto-save"] = True
    window.settings["auto-save-delay"] = 5
    try:
        tab = window.open_file(str(path))
        tab.file_manager._autosave.delay_ms = 50  # keep the test fast
        type_text(tab.editor, "b")
        tab.file_manager._autosave.delay_ms = 50
        tab.file_manager._autosave.trigger()
        assert wait_for(lambda: path.read_text() == "ab", timeout=3)
        assert not tab.file_manager.is_modified
    finally:
        window.settings["auto-save"] = False
