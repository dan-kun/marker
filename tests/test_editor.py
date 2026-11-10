"""Formatting helpers and keys on the real editor widget."""

import shutil
import subprocess

import pytest
from conftest import iterate, needs_display, wait_for

pytestmark = needs_display


def set_selection(editor, text: str):
    """Load text whose selection is marked with [ and ]."""
    start, end = text.index("["), text.index("]") - 1
    editor.set_text(text.replace("[", "").replace("]", ""))
    buf = editor.get_buffer()
    buf.select_range(buf.get_iter_at_offset(start), buf.get_iter_at_offset(end))


def marked(editor) -> str:
    buf = editor.get_buffer()
    text = editor.get_text()
    if buf.get_has_selection():
        a, b = (it.get_offset() for it in buf.get_selection_bounds())
    else:
        a = b = buf.get_iter_at_mark(buf.get_insert()).get_offset()
    return text[:a] + "[" + text[a:b] + "]" + text[b:]


@pytest.fixture
def editor(window):
    yield window.editor
    for tab in window.tab_manager.tabs():
        tab.editor.get_buffer().set_modified(False)


def test_bold_toggles_on_the_buffer(editor):
    set_selection(editor, "say [hello] now")
    editor.insert_bold()
    assert marked(editor) == "say **[hello]** now"
    editor.insert_bold()
    assert marked(editor) == "say [hello] now"


def test_formatting_at_the_edges_of_the_document(editor):
    set_selection(editor, "[x]")
    editor.insert_italic()
    assert marked(editor) == "*[x]*"
    editor.insert_bold()
    assert marked(editor) == "***[x]***"
    editor.insert_italic()
    assert marked(editor) == "**[x]**"


def test_each_format_action_is_one_undo_step(editor):
    set_selection(editor, "[word]")
    editor.insert_bold()
    editor.undo()
    assert editor.get_text() == "word"


def test_code_uses_a_fence_for_several_lines(editor):
    set_selection(editor, "[a\nb]")
    editor.insert_code()
    assert editor.get_text() == "```\na\nb\n```"
    editor.insert_code()
    assert editor.get_text() == "a\nb"


def test_heading_sets_replaces_and_removes(editor):
    set_selection(editor, "Title[]")
    editor.insert_heading(2)
    assert editor.get_text() == "## Title"
    editor.insert_heading(1)
    assert editor.get_text() == "# Title"
    editor.insert_heading(1)
    assert editor.get_text() == "Title"


def test_link_selects_the_part_to_type_next(editor):
    set_selection(editor, "see [docs] here")
    editor.insert_link()
    assert marked(editor) == "see [docs]([url]) here"
    set_selection(editor, "[]")
    editor.insert_link()
    assert marked(editor) == "[[text]](url)"


def test_lists_toggle_over_the_selected_lines(editor):
    set_selection(editor, "intro\n[a\nb]\noutro")
    editor.insert_bullet_list()
    assert editor.get_text() == "intro\n- a\n- b\noutro"
    set_selection(editor, "intro\n[- a\n- b]\noutro")
    editor.insert_bullet_list()
    assert editor.get_text() == "intro\na\nb\noutro"
    set_selection(editor, "[a\nb\nc]")
    editor.insert_numbered_list()
    assert editor.get_text() == "1. a\n2. b\n3. c"


def test_format_shortcuts_are_not_window_wide(window):
    app = window.get_application()
    for action in ("win.format-bold", "win.format-italic", "win.format-code", "win.format-link"):
        assert app.get_accels_for_action(action) == []
    assert app.get_accels_for_action("win.save-file") == ["<Control>s"]


# ── Real key presses (xdotool sends them through the X server) ─────────────

needs_xdotool = pytest.mark.skipif(shutil.which("xdotool") is None, reason="needs xdotool")


@pytest.fixture
def keyboard(window):
    """Focus the window and return a function that types keys into it."""
    found = subprocess.run(
        ["xdotool", "search", "--onlyvisible", "--name", "Marker"], capture_output=True, text=True
    ).stdout.split()
    if not found:
        pytest.skip("window not visible to xdotool")
    subprocess.run(["xdotool", "windowfocus", "--sync", found[-1]], check=False)
    assert wait_for(window.is_active, timeout=5)

    def press(*keys, text: str | None = None):
        if text is not None:
            subprocess.run(["xdotool", "type", "--delay", "5", "--", text], check=True)
        for key in keys:
            subprocess.run(["xdotool", "key", key], check=True)
        iterate(0.3)

    return press


@needs_xdotool
def test_ctrl_b_in_the_editor_formats_but_not_from_the_search_box(window, keyboard, editor):
    set_selection(editor, "[word]")
    editor.grab_focus()
    iterate(0.2)
    keyboard("ctrl+b")
    assert editor.get_text() == "**word**"

    window.activate_action("win.find", None)
    iterate(0.2)
    keyboard("ctrl+b", "ctrl+i", "ctrl+l")
    assert editor.get_text() == "**word**"  # untouched while typing in "Find…"


@needs_xdotool
def test_enter_continues_and_ends_lists(window, keyboard, editor):
    editor.set_text("")
    editor.grab_focus()
    iterate(0.2)
    keyboard(text="- one")
    keyboard("Return")
    keyboard(text="two")
    assert editor.get_text() == "- one\n- two"
    keyboard("Return")
    assert editor.get_text() == "- one\n- two\n- "
    keyboard("Return")  # empty item: leave the list
    assert editor.get_text() == "- one\n- two\n"
    keyboard(text="1. a")
    keyboard("Return")
    assert editor.get_text() == "- one\n- two\n1. a\n2. "


@needs_xdotool
def test_tab_nests_list_items_only(window, keyboard, editor):
    editor.set_text("- item")
    editor.grab_focus()
    iterate(0.2)
    editor.get_buffer().place_cursor(editor.get_buffer().get_end_iter())
    keyboard("Tab")
    assert editor.get_text() == "    - item"
    keyboard("shift+Tab")
    assert editor.get_text() == "- item"
