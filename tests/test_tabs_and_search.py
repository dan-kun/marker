"""Tabs, search and sidebar behaviour."""

from conftest import iterate, needs_display, wait_for

pytestmark = needs_display


def test_open_reuses_blank_tab_and_existing_tabs(window, tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("A")
    b.write_text("B")
    tm = window.tab_manager
    tab_a = window.open_file(str(a))
    assert len(tm.tabs()) == 1  # the blank start tab was reused
    tab_b = window.open_file(str(b))
    assert len(tm.tabs()) == 2 and tab_b is not tab_a
    assert window.open_file(str(a)) is tab_a
    assert len(tm.tabs()) == 2 and tm.active_tab is tab_a


def test_explorer_root_only_changes_for_files_outside_it(window, tmp_path):
    (tmp_path / "docs").mkdir()
    inner = tmp_path / "docs" / "inner.md"
    inner.write_text("x")
    window.file_explorer.set_root(str(tmp_path))
    window.open_file(str(inner))
    assert window.file_explorer.root_path == str(tmp_path)


def test_settings_apply_to_every_tab(window):
    first = window.tab_manager.active_tab
    second = window.tab_manager.new_tab()
    window.settings["tab-width"] = 7
    try:
        assert first.editor.get_view().get_tab_width() == 7
        assert second.editor.get_view().get_tab_width() == 7
        third = window.tab_manager.new_tab()
        assert third.editor.get_view().get_tab_width() == 7
    finally:
        window.settings["tab-width"] = 4


def test_closed_tabs_are_released(window):
    import gc
    import weakref

    tab = window.tab_manager.new_tab()
    preview_ref = weakref.ref(tab.preview)
    window.tab_manager.close_active_tab()
    del tab
    iterate(0.2)
    gc.collect()
    assert preview_ref() is None


def test_find_next_advances(window):
    editor = window.editor
    editor.set_text("foo bar foo baz foo")
    bar = window.search_bar
    bar.show_search()
    bar._search_entry.set_text("foo")
    assert wait_for(lambda: bar._match_label.get_text() == "3 found")

    offsets = []
    for _ in range(4):
        bar._on_find_next()
        start, _ = editor.get_buffer().get_selection_bounds()
        offsets.append(start.get_offset())
    assert offsets == [0, 8, 16, 0]  # wraps around

    bar._on_find_prev()
    start, _ = editor.get_buffer().get_selection_bounds()
    assert start.get_offset() == 16


def test_replace_then_moves_to_next_match(window):
    editor = window.editor
    editor.set_text("a x a x")
    bar = window.search_bar
    bar.show_replace()
    bar._search_entry.set_text("a")
    bar._replace_entry.set_text("b")
    iterate(0.1)
    bar._on_replace()
    bar._on_replace()
    assert editor.get_text() == "b x b x"


def test_invalid_regex_is_reported(window):
    bar = window.search_bar
    bar.show_search()
    bar._btn_regex.set_active(True)
    bar._search_entry.set_text("(")
    assert wait_for(lambda: bar._match_label.get_text() == "Invalid regex")
    bar._btn_regex.set_active(False)


def test_escape_closes_search(window):
    bar = window.search_bar
    bar.show_search()
    bar._search_entry.emit("stop-search")
    assert not bar.get_visible()


def test_folder_search_opens_result_once_at_the_line(window, tmp_path):
    (tmp_path / "notes.md").write_text("one\ntwo\n--weird: query\n")
    (tmp_path / "other.md").write_text("--weird: query too\n")
    window.file_explorer.set_root(str(tmp_path))
    bar = window.search_bar
    bar.show_dir_search()
    bar._dir_entry.set_text("--weird: query")  # starts with "-" and has ":"
    bar._on_dir_search()
    assert wait_for(lambda: getattr(bar._dir_results.get_row_at_index(1), "location", None))

    opened = []
    window.tab_manager.connect("file-opened", lambda tm, path: opened.append(path))
    rows = [bar._dir_results.get_row_at_index(i) for i in range(2)]
    row = next(r for r in rows if r.location[0].endswith("notes.md"))
    bar._dir_results.emit("row-activated", row)
    iterate(0.1)
    assert opened == [str(tmp_path / "notes.md")]
    assert window.editor.get_cursor_position() == (3, 1)


def test_explorer_keeps_expanded_folders_on_refresh(window, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.md").write_text("x")
    explorer = window.file_explorer
    explorer.set_root(str(tmp_path))
    dir_row = explorer._list_box.get_row_at_index(0)
    explorer._list_box.emit("row-activated", dir_row)
    assert explorer._list_box.get_row_at_index(1).path.endswith("x.md")

    (tmp_path / "sub" / "y.md").write_text("y")
    assert wait_for(lambda: (r := explorer._list_box.get_row_at_index(2)) is not None
                    and r.path.endswith("y.md"), timeout=5)


def test_view_mode_buttons_follow_the_active_tab(window):
    tm = window.tab_manager
    first = tm.active_tab
    window.activate_action("win.preview-only", None)
    assert first.split_view.get_mode() == "preview"
    second = tm.new_tab()
    assert window.lookup_action("view-mode").get_state().get_string() == "split"
    tm.select(first)
    assert window.lookup_action("view-mode").get_state().get_string() == "preview"
    assert second.split_view.get_mode() == "split"


def test_editor_scroll_is_mirrored_in_the_preview(window, monkeypatch):
    tab = window.tab_manager.active_tab
    fractions = []
    monkeypatch.setattr(tab.preview, "scroll_to_fraction", fractions.append)
    tab.editor.set_text("line\n" * 2000)
    vadj = tab.editor.get_vadjustment()
    assert wait_for(lambda: vadj.get_upper() > vadj.get_page_size() * 2)
    vadj.set_value((vadj.get_upper() - vadj.get_page_size()) / 2)
    assert wait_for(lambda: fractions)
    assert abs(fractions[-1] - 0.5) < 0.05


def test_minimap_viewport_matches_drawn_lines_for_short_documents(window):
    minimap = window._minimap
    window.editor.set_text("# Title\n" + "text\n" * 5)
    assert wait_for(lambda: len(minimap._lines) == 7)
    scale, content_h = minimap._layout(600)
    assert scale == 1.0
    assert content_h == minimap.HEADING_HEIGHT + 6 * minimap.LINE_HEIGHT  # not the widget height
