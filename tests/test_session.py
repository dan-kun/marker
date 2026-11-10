"""Remembered window state, external file changes, and auto-save status."""

import json
import os

from conftest import iterate, needs_display, wait_for

from marker import session
from marker.utils import config_path


def test_session_load_ignores_malformed_values(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({
        "width": "wide", "height": 900, "view-mode": "sideways", "zoom": 99,
        "files": ["a.md", 3], "sidebar": False, "unknown": 1,
    }))
    state = session.load(str(path))
    assert state["width"] == session.DEFAULTS["width"]
    assert state["height"] == 900
    assert state["view-mode"] == "split" and state["zoom"] == 1.0 and state["files"] == []
    assert state["sidebar"] is False
    assert "unknown" not in state

    path.write_text("not json")
    assert session.load(str(path)) == session.DEFAULTS


def touch_later(path, text):
    """Rewrite path as another program would, with a clearly newer mtime."""
    stat = os.stat(path)
    path.write_text(text)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2 * 10**9))


def type_text(editor, text):
    buf = editor.get_buffer()
    buf.begin_user_action()
    buf.insert(buf.get_end_iter(), text)
    buf.end_user_action()


@needs_display
def test_layout_and_documents_are_restored(app, tmp_path):
    from marker.window import MarkerWindow

    if os.path.exists(config_path("session.json")):
        os.unlink(config_path("session.json"))
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("A")
    b.write_text("B")
    gone = tmp_path / "gone.md"
    gone.write_text("x")

    first = MarkerWindow(application=app)
    first.present()
    iterate(0.2)
    first.file_explorer.set_root(str(tmp_path))
    first.open_file(str(a))
    first.open_file(str(gone))
    first.open_file(str(b))
    first.activate_action("win.editor-only", None)
    first.activate_action("win.show-sidebar", None)
    first.activate_action("win.show-minimap", None)
    first.activate_action("win.zoom-in", None)
    first.set_default_size(900, 600)
    first.close()
    iterate(0.2)
    gone.unlink()

    second = MarkerWindow(application=app)
    try:
        second.present()
        second.restore_documents()
        iterate(0.2)
        assert second.lookup_action("view-mode").get_state().get_string() == "editor"
        assert not second.lookup_action("show-sidebar").get_state().get_boolean()
        assert not second._minimap.get_visible()
        assert second.tab_manager.zoom == 1.1
        assert second.file_explorer.root_path == str(tmp_path)
        paths = [t.file_manager.current_path for t in second.tab_manager.tabs()]
        assert paths == [str(a), str(b)]  # the deleted file is skipped quietly
        assert second.file_manager.current_path == str(b)
        assert all(t.editor.zoom_level == 1.1 for t in second.tab_manager.tabs())
        assert second.tab_manager.new_tab().editor.zoom_level == 1.1
    finally:
        second.close()
        iterate(0.1)
        saved = session.load()
        os.unlink(config_path("session.json"))
    # two open/close cycles later the size is still what the user chose
    assert (saved["width"], saved["height"]) == (900, 600)


@needs_display
def test_external_change_reloads_a_clean_tab_and_keeps_the_cursor(window, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("one\ntwo\nthree\n")
    tab = window.open_file(str(path))
    tab.editor.set_cursor_position(2, 2)

    touch_later(path, "zero\none\ntwo\nthree\n")
    assert wait_for(lambda: tab.editor.get_text().startswith("zero"), timeout=5)
    assert not tab.file_manager.is_modified
    assert tab.editor.get_cursor_position() == (2, 2)
    assert not window._conflict_bar.get_visible()


@needs_display
def test_external_change_with_unsaved_edits_shows_a_notice(window, tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("v1")
    tab = window.open_file(str(path))
    type_text(tab.editor, " mine")

    touch_later(path, "theirs")
    assert wait_for(window._conflict_bar.get_visible, timeout=5)
    assert tab.editor.get_text() == "v1 mine"  # never replaced behind the user's back

    # the notice follows the active tab
    other = window.tab_manager.new_tab()
    assert not window._conflict_bar.get_visible()
    window.tab_manager.select(tab)
    assert window._conflict_bar.get_visible()

    tab.file_manager.dismiss_disk_change()
    assert not window._conflict_bar.get_visible()
    tab.file_manager.reload(discard=True)
    assert tab.editor.get_text() == "theirs" and not tab.file_manager.is_modified
    other.editor.get_buffer().set_modified(False)


@needs_display
def test_save_as_onto_an_open_file_closes_the_stale_tab(window, save_as, tmp_path):
    path = tmp_path / "a.md"
    path.write_text("old")
    window.open_file(str(path))
    draft = window.tab_manager.new_tab()
    type_text(draft.editor, "new")
    save_as.path = str(path)
    draft.file_manager.save_file_as()
    iterate(0.2)
    assert window.tab_manager.tabs() == [draft]
    assert path.read_text() == "new"


@needs_display
def test_failed_autosave_reports_in_the_status_bar_without_dialogs(window, dialogs_log, monkeypatch,
                                                                    tmp_path):
    from marker import file_manager

    path = tmp_path / "auto.md"
    path.write_text("a")
    tab = window.open_file(str(path))
    type_text(tab.editor, "b")

    def fail(*args, **kwargs):
        raise OSError(28, "No space left on device")

    real_write = file_manager.write_text_file
    monkeypatch.setattr(file_manager, "write_text_file", fail)
    for _ in range(3):
        tab.file_manager._on_autosave()
    assert dialogs_log == []
    assert window._status_save.get_text() == "Auto-save paused: No space left on device"
    assert tab.file_manager.is_modified

    monkeypatch.setattr(file_manager, "write_text_file", real_write)
    tab.file_manager._on_autosave()
    assert path.read_text() == "ab"
    assert window._status_save.get_text() == "Saved just now"


@needs_display
def test_reload_action_asks_before_dropping_edits(window, dialogs_log, tmp_path):
    path = tmp_path / "a.md"
    path.write_text("disk")
    tab = window.open_file(str(path))
    type_text(tab.editor, " edit")
    window.activate_action("win.reload", None)
    dialogs_log[-1].respond("cancel")
    assert tab.editor.get_text() == "disk edit"
    window.activate_action("win.reload", None)
    dialogs_log[-1].respond("discard")
    assert tab.editor.get_text() == "disk"
