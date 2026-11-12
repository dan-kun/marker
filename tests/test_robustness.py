"""Regression tests for the faults found by the adversarial review:
data loss, the split divider, the session, the sidebar and the preview."""

import json
import os
import stat

import pytest
from conftest import iterate, needs_display, wait_for
from test_editor import set_selection
from test_preview import content_text, js, render
from test_session import touch_later, type_text
from test_tabs_and_search import explorer_rows

from marker import session, textio
from marker.search import grep_argv
from marker.titles import display, short_labels
from marker.utils import config_path

# ── Data loss ──────────────────────────────────────────────────────────────


def test_a_nul_byte_anywhere_marks_the_file_as_binary():
    # The text view would cut the document at the NUL and the next save
    # would write the shortened text back.
    data = b"line\n" * 2600 + b"\x00" + b"more\n" * 600
    assert data.index(b"\x00") > 8192
    with pytest.raises(textio.BinaryFileError):
        textio.decode(data)


def test_read_only_files_are_not_replaced(tmp_path):
    path = tmp_path / "locked.md"
    path.write_text("keep me")
    path.chmod(0o444)
    with pytest.raises(PermissionError):
        textio.write_text_file(str(path), "overwritten")
    assert path.read_text() == "keep me"
    assert stat.S_IMODE(path.stat().st_mode) == 0o444
    assert not [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]


def test_names_that_are_not_utf8_can_be_displayed():
    name = os.fsdecode(b"caf\xe9.md")
    assert display(name) == "caf\ufffd.md"
    assert display("plain.md") == "plain.md"
    assert short_labels([f"/a/{name}"]) == {f"/a/{name}": "caf\ufffd.md"}


# ── Split divider ──────────────────────────────────────────────────────────


def preview_share(tab) -> float:
    """Share of the tab's width taken by the editor."""
    return tab.split_view.get_position() / tab.split_view.get_width()


@needs_display
def test_tabs_opened_together_all_get_a_usable_preview(window, tmp_path):
    paths = []
    for name in ("one", "two", "three"):
        path = tmp_path / f"{name}.md"
        path.write_text(f"# {name}\n")
        paths.append(str(path))
    for path in paths:  # as "Open" with several files selected, or the command line
        window.open_file(path)
    iterate(0.3)

    for tab in window.tab_manager.tabs():
        window.tab_manager.select(tab)
        iterate(0.3)
        assert window.preview.get_width() > 200, tab.file_manager.display_name
        assert 0.45 < preview_share(tab) < 0.55


@needs_display
def test_the_divider_is_shared_by_tabs_and_remembered(window, tmp_path):
    first = window.tab_manager.active_tab
    iterate(0.3)
    first.split_view.set_position(round(first.split_view.get_width() * 0.3))
    iterate(0.2)
    assert 0.28 < window.tab_manager.divider.fraction < 0.32

    second = window.tab_manager.new_tab()
    iterate(0.3)
    assert 0.28 < preview_share(second) < 0.32

    window._save_session()
    assert 0.28 < session.load()["split"] < 0.32


# ── Session ────────────────────────────────────────────────────────────────


@needs_display
def test_opening_a_file_from_the_command_line_keeps_the_saved_session(app, tmp_path):
    from gi.repository import Gio

    old = [tmp_path / "a.md", tmp_path / "b.md"]
    new = tmp_path / "other" / "c.md"
    new.parent.mkdir()
    for path in (*old, new):
        path.write_text(path.name)
    state = dict(session.DEFAULTS, files=[str(p) for p in old], folders=[str(tmp_path)])
    session.save(state)
    assert not app.get_windows()

    app._on_open(app, [Gio.File.new_for_path(str(new))], 1, "")  # "marker other/c.md"
    window = app.get_windows()[0]
    try:
        iterate(0.2)
        paths = [t.file_manager.current_path for t in window.tab_manager.tabs()]
        assert paths == [str(old[0]), str(old[1]), str(new)]
        assert window.file_manager.current_path == str(new)
    finally:
        window.close()
        iterate(0.2)
    saved = session.load()
    os.unlink(config_path("session.json"))
    assert saved["files"] == [str(old[0]), str(old[1]), str(new)]


# ── Editor ─────────────────────────────────────────────────────────────────


@needs_display
def test_a_search_result_in_an_unopened_file_scrolls_to_its_line(window, tmp_path):
    path = tmp_path / "long.md"
    path.write_text("".join(f"line {n}\n" for n in range(1, 4001)))
    window.search_bar.emit("open-location", str(path), 2999)
    assert window.editor.get_cursor_position() == (3000, 1)
    # the line is on screen, not just where the cursor is
    assert wait_for(lambda: 2900 < window.editor.get_top_line() <= 2999, timeout=5)


@needs_display
def test_code_block_takes_whole_lines(window):
    editor = window.editor
    set_selection(editor, "before te[xt\nsecond li]ne after")
    editor.insert_code()
    assert editor.get_text() == "```\nbefore text\nsecond line after\n```"
    editor.insert_code()  # and comes off again
    assert editor.get_text() == "before text\nsecond line after"
    editor.get_buffer().set_modified(False)


@needs_display
def test_list_keys_are_for_prose_not_source_code(window, tmp_path):
    script = tmp_path / "script.py"
    script.write_text("- not a list\n")
    tab = window.open_file(str(script))
    assert not tab.editor._list_keys
    assert window._status_syntax.get_text() == "Python"
    notes = tmp_path / "notes.txt"
    notes.write_text("- a list\n")
    assert window.open_file(str(notes)).editor._list_keys


@needs_display
def test_list_items_nest_by_four_spaces_whatever_the_tab_width(window):
    editor = window.editor
    editor.get_view().set_tab_width(2)
    editor.set_text("1. item")
    editor.get_buffer().place_cursor(editor.get_buffer().get_end_iter())
    assert editor._indent_list_item(unindent=False)
    assert editor.get_text() == "    1. item"   # two spaces would not nest under "1."
    assert editor._indent_list_item(unindent=True)
    assert editor.get_text() == "1. item"

    # inside a code block, "- x" is code: Enter and Tab are left to the editor
    editor.set_text("```\n- x")
    editor.get_buffer().place_cursor(editor.get_buffer().get_end_iter())
    assert not editor._continue_list()
    assert not editor._indent_list_item(unindent=False)
    editor.get_buffer().set_modified(False)


@needs_display
def test_changing_view_mode_keeps_the_keyboard_focus(window):
    window.editor.grab_focus()
    window.activate_action("win.preview-only", None)
    iterate(0.2)
    focus = window.get_focus()
    assert focus is not None and focus.is_ancestor(window.preview)
    window.activate_action("win.editor-only", None)
    iterate(0.2)
    assert window.get_focus() is window.editor.get_view()


@needs_display
def test_preview_only_hides_the_minimap_and_find_brings_the_editor_back(window):
    window.activate_action("win.preview-only", None)
    assert not window._minimap.get_visible()
    window.activate_action("win.find", None)
    assert window.split_view.get_mode() == "split"
    assert window._minimap.get_visible() and window.editor.get_visible()


@needs_display
def test_tab_switching_wraps_around(window):
    tabs = [window.tab_manager.active_tab, window.tab_manager.new_tab(), window.tab_manager.new_tab()]
    window.tab_manager.next_tab()
    assert window.tab_manager.active_tab is tabs[0]
    window.tab_manager.prev_tab()
    assert window.tab_manager.active_tab is tabs[2]


@needs_display
def test_edit_menu_actions_reach_the_editor(window):
    type_text(window.editor, "hello")
    window.activate_action("win.undo", None)
    assert window.editor.get_text() == ""
    window.activate_action("win.redo", None)
    assert window.editor.get_text() == "hello"
    window.editor.get_buffer().set_modified(False)


# ── Changes made by other programs ─────────────────────────────────────────


@needs_display
def test_keeping_my_edits_is_not_undone_by_autosave(window, tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("original\n")
    tab = window.open_file(str(path))
    fm = tab.file_manager
    type_text(tab.editor, "mine")
    touch_later(path, "theirs\n")
    assert wait_for(lambda: fm.changed_on_disk)

    fm.dismiss_disk_change()
    assert not window._conflict_bar.get_visible()
    fm._on_autosave()  # the next auto-save tick
    assert not fm.changed_on_disk and not window._conflict_bar.get_visible()
    assert fm.autosave_problem == "the file changed on disk"
    assert path.read_text() == "theirs\n"   # and still nothing is overwritten

    touch_later(path, "theirs again\n")      # a further change is news again
    assert wait_for(lambda: fm.changed_on_disk)


@needs_display
def test_a_file_deleted_by_another_program_is_noticed(window, tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("only copy\n")
    fm = window.open_file(str(path)).file_manager
    path.unlink()
    assert wait_for(lambda: fm.missing_on_disk)
    assert window._conflict_bar.get_visible()
    assert "deleted or moved" in window._conflict_label.get_text()
    assert window._conflict_save.get_visible() and not window._conflict_reload.get_visible()

    window._conflict_save.emit("clicked")
    assert path.read_text() == "only copy\n"
    assert not fm.missing_on_disk and not window._conflict_bar.get_visible()


@needs_display
def test_reload_keeps_the_cursor(window, tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("one\ntwo\nthree\n")
    tab = window.open_file(str(path))
    opened = []
    window.tab_manager.connect("file-opened", lambda tm, p: opened.append(p))
    tab.editor.set_cursor_position(3, 2)
    path.write_text("one\ntwo\nthree\nfour\n")
    window.activate_action("win.reload", None)
    assert tab.editor.get_text().endswith("four\n")
    assert tab.editor.get_cursor_position() == (3, 2)
    assert opened == []  # a reload is not an open: the sidebar does not react


# ── Sidebar ────────────────────────────────────────────────────────────────


def row_names(explorer):
    return [(row.depth, os.path.basename(row.path)) for row in explorer_rows(explorer)]


@needs_display
def test_a_folder_inside_another_is_never_listed_twice(window, tmp_path):
    inner = tmp_path / "outer" / "inner"
    inner.mkdir(parents=True)
    (inner / "note.md").write_text("x")
    explorer = window.file_explorer
    outer = str(tmp_path / "outer")

    explorer.add_root(outer)
    explorer.add_root(str(inner))  # already shown: opened in place, not added
    assert explorer.roots == [outer]
    assert row_names(explorer) == [(0, "outer"), (1, "inner"), (2, "note.md")]

    # the other way round: the parent takes the place of what it contains
    explorer.set_roots([str(inner)])
    explorer.add_root(outer)
    assert explorer.roots == [outer]
    assert row_names(explorer) == [(0, "outer"), (1, "inner"), (2, "note.md")]

    # collapsing and expanding never duplicates rows
    inner_row = explorer_rows(explorer)[1]
    for _ in range(2):
        explorer._list_box.emit("row-activated", inner_row)
        inner_row = explorer_rows(explorer)[1]
    assert row_names(explorer) == [(0, "outer"), (1, "inner"), (2, "note.md")]

    explorer.set_roots([str(inner), outer, str(inner)])  # e.g. an older session file
    assert explorer.roots == [outer]


@needs_display
def test_a_file_name_that_is_not_utf8_does_not_break_the_tree(window, tmp_path):
    folder = os.fsencode(str(tmp_path))
    try:
        with open(os.path.join(folder, b"caf\xe9.md"), "wb") as f:
            f.write(b"x")
    except OSError:
        pytest.skip("this filesystem only takes UTF-8 names")
    (tmp_path / "zz.md").write_text("x")
    window.file_explorer.set_roots([str(tmp_path)])
    names = [os.path.basename(row.path) for row in explorer_rows(window.file_explorer)]
    assert names == [tmp_path.name, os.fsdecode(b"caf\xe9.md"), "zz.md"]
    assert window.open_file(os.path.join(str(tmp_path), os.fsdecode(b"caf\xe9.md"))) is not None
    assert window.tab_manager.active_tab.page.get_title() == "caf\ufffd.md"


@needs_display
def test_refreshing_the_tree_keeps_rows_selection_and_scroll(window, tmp_path):
    for n in range(60):
        (tmp_path / f"file{n:02}.md").write_text("x")
    explorer = window.file_explorer
    explorer.set_roots([str(tmp_path)])
    iterate(0.3)
    rows = explorer_rows(explorer)
    explorer._list_box.select_row(rows[40])
    adjustment = explorer._scrolled.get_vadjustment()
    adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
    scrolled_to = adjustment.get_value()
    assert scrolled_to > 0

    explorer._refresh()  # nothing changed on disk: nothing is rebuilt
    iterate(0.2)
    assert explorer_rows(explorer) == rows
    assert explorer._list_box.get_selected_row() is rows[40]
    assert adjustment.get_value() == scrolled_to

    (tmp_path / "file10.md").unlink()
    (tmp_path / "file99.md").write_text("x")
    explorer._refresh()
    iterate(0.2)
    after = explorer_rows(explorer)
    assert len(after) == len(rows)
    assert after[:11] == rows[:11] and after[11:-1] == rows[12:]  # only the changed rows differ
    assert explorer._list_box.get_selected_row() is rows[40]
    assert adjustment.get_value() > 0


@needs_display
def test_switching_tabs_does_not_bring_back_a_removed_folder(window, tmp_path):
    (tmp_path / "work" / "docs").mkdir(parents=True)
    (tmp_path / "home").mkdir()
    work, deep, home = tmp_path / "work" / "a.md", tmp_path / "work" / "docs" / "b.md", \
        tmp_path / "home" / "c.md"
    for path in (work, deep, home):
        path.write_text("x")
    explorer = window.file_explorer
    work_tab = window.open_file(str(work))
    deep_tab = window.open_file(str(deep))
    home_tab = window.open_file(str(home))
    assert explorer.roots == [str(tmp_path / "work"), str(tmp_path / "home")]

    explorer.remove_root(str(tmp_path / "home"))
    window.tab_manager.select(work_tab)
    window.tab_manager.select(home_tab)
    assert explorer.roots == [str(tmp_path / "work")]  # the "×" is respected

    # a folder the user closed stays closed; its file is simply not selected
    docs_row = next(r for r in explorer_rows(explorer) if r.path == str(tmp_path / "work" / "docs"))
    explorer._list_box.emit("row-activated", docs_row)
    window.tab_manager.select(deep_tab)
    assert (2, "b.md") not in row_names(explorer)
    assert explorer._list_box.get_selected_row() is None
    window.tab_manager.select(work_tab)
    assert explorer._list_box.get_selected_row().path == str(work)


@needs_display
def test_a_deleted_folder_leaves_the_sidebar(window, tmp_path):
    keep, doomed = tmp_path / "keep", tmp_path / "doomed"
    keep.mkdir()
    doomed.mkdir()
    explorer = window.file_explorer
    explorer.set_roots([str(keep), str(doomed)])
    doomed.rmdir()
    assert wait_for(lambda: explorer.roots == [str(keep)], timeout=5)


# ── Folder search ──────────────────────────────────────────────────────────


def test_folder_search_ignores_case_unless_asked():
    assert "-i" in grep_argv("x") and "-i" not in grep_argv("x", match_case=True)
    assert "--include=*.[mM][dD]" in grep_argv("x")


@needs_display
def test_folder_search_finds_other_case_and_uppercase_extensions(window, tmp_path):
    (tmp_path / "README.MD").write_text("A Needle here\n")
    (tmp_path / "lower.md").write_text("needle\n")
    window.file_explorer.set_roots([str(tmp_path)])
    bar = window.search_bar
    bar.show_dir_search()

    def search():
        bar._on_dir_search()
        assert wait_for(lambda: not bar._grep_processes, timeout=10)
        iterate(0.1)
        rows = (bar._dir_results.get_row_at_index(i) for i in range(5))
        return sorted(os.path.basename(r.location[0]) for r in rows if hasattr(r, "location"))

    bar._dir_entry.set_text("needle")
    assert search() == ["README.MD", "lower.md"]
    bar._btn_dir_case.set_active(True)
    assert search() == ["lower.md"]
    bar._btn_dir_case.set_active(False)


# ── Preview ────────────────────────────────────────────────────────────────


@pytest.fixture
def preview(window):
    assert wait_for(lambda: window.preview._ready, timeout=15)
    return window.preview


@needs_display
def test_prices_are_not_formulas_and_formulas_keep_their_backslashes(preview):
    render(preview, "From $5 to $50, or $a_1 + b_2$ and \\(x^2\\).\n\n"
                    "$$\n\\begin{aligned} a &= \\{1\\} \\\\ b &= 2 \\end{aligned}\n$$\n\n"
                    "`$not math$` and \\$9.\n")
    assert wait_for(lambda: js(preview, "return document.querySelectorAll('.katex').length") == 3)
    text = content_text(preview)
    assert "From $5 to $50, or" in text and "$not math$" in text and "$9." in text
    assert js(preview, "return document.querySelectorAll('.katex-error').length") == 0
    # the display formula kept both rows: "\\\\" was not eaten by Markdown
    rows = js(preview, "return document.querySelector('.math-display .katex-html')"
                       ".querySelectorAll('.col-align-r > .vlist-t > .vlist-r > .vlist > span').length")
    assert rows >= 2
    # it also knows which source lines it came from, for scroll sync
    assert js(preview, "return document.querySelector('.math-display').dataset.line") == "2"


@needs_display
def test_style_elements_are_removed_wherever_they_are(preview):
    render(preview, "text\n\n<p>para</p><style>#content { display: none !important }</style>\n")
    assert js(preview, "return document.querySelectorAll('#content style').length") == 0
    assert js(preview, "return getComputedStyle(document.getElementById('content')).display") == "block"


@needs_display
def test_a_heading_called_mermaid_does_not_break_diagrams(preview):
    render(preview, "# Mermaid\n\ntext\n")
    preview._js_set_theme()  # used to throw: window.mermaid was the heading
    render(preview, "# Mermaid\n\n```mermaid\ngraph TD; A-->B;\n```\n")
    assert wait_for(lambda: js(preview, "return document.querySelectorAll('.mermaid svg').length") == 1,
                    timeout=20)

    # switching theme redraws the diagram in the new colours
    preview._is_dark = not preview._is_dark
    preview._js_set_theme()
    key = "dark|" if preview._is_dark else "light|"
    try:
        assert wait_for(lambda: js(preview, "return [..._mermaidCache.keys()]"
                                            f".some(k => k.startsWith('{key}'))"), timeout=20)
    finally:
        preview._is_dark = not preview._is_dark
        preview._js_set_theme()


@needs_display
def test_files_that_are_not_markdown_are_shown_as_source(preview, window, tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("# not a heading\nimport os\nprint('*not emphasis*')\n")
    window.open_file(str(script))
    assert wait_for(lambda: js(preview, "return document.querySelectorAll('pre.source-file').length") == 1)
    assert js(preview, "return document.querySelectorAll('#content h1, #content em').length") == 0
    assert js(preview, "return document.querySelectorAll('.hljs-keyword').length") >= 1
    assert content_text(preview) == script.read_text().strip()

    # a Markdown tab still renders as Markdown, and switching back keeps the source view
    doc = tmp_path / "doc.md"
    doc.write_text("# a heading\n")
    window.open_file(str(doc))
    assert wait_for(lambda: js(preview, "return document.querySelectorAll('#content h1').length") == 1)


@needs_display
def test_renders_requested_while_one_is_running_collapse_into_one(preview):
    sent = []
    webview = preview.get_webview()
    original = webview.evaluate_javascript

    def counting(script, *args):
        sent.append(script)
        return original(script, *args)

    assert wait_for(lambda: not preview._render_running)
    webview.evaluate_javascript = counting
    try:
        for n in range(6):
            preview.render(f"version {n}")
        assert wait_for(lambda: content_text(preview) == "version 5")
    finally:
        del webview.evaluate_javascript
    assert len([s for s in sent if s.startswith("render(")]) == 2  # the first, then the latest


# ── Window chrome ──────────────────────────────────────────────────────────


@needs_display
def test_menus_and_tooltips_show_names_as_they_are(window, tmp_path):
    path = tmp_path / "my_notes & <ideas>.md"
    path.write_text("x")
    tab = window.open_file(str(path))
    assert tab.page.get_tooltip() == str(path).replace("&", "&amp;").replace("<", "&lt;") \
        .replace(">", "&gt;")
    files = window._recents_menu.get_item_link(0, "section")
    label = files.get_item_attribute_value(0, "label", None).get_string()
    assert label == "my__notes & <ideas>.md"  # "_" doubled: a single one marks a mnemonic


@needs_display
def test_title_shows_the_folder_and_the_status_bar_has_no_stray_separator(window, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "notes").mkdir()
    path = tmp_path / "notes" / "todo.md"
    path.write_text("x")
    assert not window._status_save_separator.get_visible()  # nothing saved yet: nothing to separate
    window.open_file(str(path))
    assert window._title_label.get_text() == "todo.md"
    assert window._subtitle_label.get_text() == "~/notes"
    type_text(window.editor, "y")
    assert window._status_save.get_text() == "Modified"
    assert window._status_save_separator.get_visible()
    window.editor.get_buffer().set_modified(False)


def test_session_file_rejects_a_bad_divider(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"split": 0.99}))
    assert session.load(str(path))["split"] == 0.5
    path.write_text(json.dumps({"split": 0.3}))
    assert session.load(str(path))["split"] == 0.3
