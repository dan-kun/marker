"""Working with files from several folders: tab titles, sidebar, search."""

import json
import os

from conftest import iterate, needs_display, wait_for
from test_tabs_and_search import explorer_rows

from marker import session
from marker.search import search_roots
from marker.titles import short_labels


def test_short_labels_add_only_what_is_needed():
    assert short_labels(["/w/a.md", "/w/b.md"]) == {"/w/a.md": "a.md", "/w/b.md": "b.md"}
    assert short_labels(["/work/README.md", "/home/notes/README.md", "/x/ideas.md"]) == {
        "/work/README.md": "README.md — work",
        "/home/notes/README.md": "README.md — notes",
        "/x/ideas.md": "ideas.md",
    }
    # same parent name: go one level further up
    assert short_labels(["/a/docs/x.md", "/b/docs/x.md"]) == {
        "/a/docs/x.md": "x.md — a/docs", "/b/docs/x.md": "x.md — b/docs",
    }
    # folders work too, and duplicates do not count as a clash
    assert short_labels(["/a/notes", "/b/notes", "/a/notes"]) == {
        "/a/notes": "notes — a", "/b/notes": "notes — b",
    }
    assert short_labels(["/x.md", "/a/x.md"]) == {"/x.md": "x.md", "/a/x.md": "x.md — a"}


def test_search_roots_skip_missing_and_nested_folders(tmp_path):
    (tmp_path / "a" / "inner").mkdir(parents=True)
    (tmp_path / "ab").mkdir()
    a, inner, ab = (str(tmp_path / p) for p in ("a", "a/inner", "ab"))
    assert search_roots([inner, a, ab, a, str(tmp_path / "gone")]) == [a, ab]


def test_old_single_folder_sessions_still_load(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"folder": "/old/place", "files": []}))
    assert session.load(str(path))["folders"] == ["/old/place"]


def make_tree(tmp_path):
    for folder in ("work", "home/notes", "other"):
        (tmp_path / folder).mkdir(parents=True)
    files = {
        "work": tmp_path / "work" / "README.md",
        "notes": tmp_path / "home" / "notes" / "README.md",
        "ideas": tmp_path / "other" / "ideas.md",
    }
    for name, path in files.items():
        path.write_text(f"# {name}\nneedle in {name}\n")
    return files


def titles(window):
    return [tab.page.get_title() for tab in window.tab_manager.tabs()]


def selected_path(explorer):
    row = explorer._list_box.get_selected_row()
    return row.path if row is not None else None


@needs_display
def test_tabs_with_the_same_file_name_show_their_folder(window, save_as, tmp_path):
    files = make_tree(tmp_path)
    window.open_file(str(files["work"]))
    assert titles(window) == ["README.md"]
    notes_tab = window.open_file(str(files["notes"]))
    window.open_file(str(files["ideas"]))
    assert titles(window) == ["README.md — work", "README.md — notes", "ideas.md"]

    # once the clash is gone the plain name comes back
    window.tab_manager.select(notes_tab)
    window.tab_manager.close_active_tab()
    iterate(0.2)
    assert titles(window) == ["README.md", "ideas.md"]

    # "Save As" into a clash updates both tabs
    save_as.path = str(tmp_path / "other" / "README.md")
    window.tab_manager.tabs()[1].file_manager.save_file_as()
    assert titles(window) == ["README.md — work", "README.md — other"]


@needs_display
def test_sidebar_shows_several_folders_and_follows_the_active_tab(window, tmp_path):
    files = make_tree(tmp_path)
    explorer = window.file_explorer
    work_tab = window.open_file(str(files["work"]))
    assert explorer.roots == [str(tmp_path / "work")]
    notes_tab = window.open_file(str(files["notes"]))
    # the first folder stays; the new file's folder is added next to it
    assert explorer.roots == [str(tmp_path / "work"), str(tmp_path / "home" / "notes")]
    assert selected_path(explorer) == str(files["notes"])

    window.tab_manager.select(work_tab)
    assert selected_path(explorer) == str(files["work"])
    window.tab_manager.new_tab()  # untitled: nothing to point at
    assert selected_path(explorer) is None

    # both roots are in the tree, each with its own files
    shown = [(row.depth, os.path.basename(row.path)) for row in explorer_rows(explorer)]
    assert shown == [(0, "work"), (1, "README.md"), (0, "notes"), (1, "README.md")]

    # a file in a subfolder of a root opens that subfolder instead of adding a root
    deep = tmp_path / "work" / "docs" / "guide.md"
    deep.parent.mkdir()
    deep.write_text("guide")
    window.open_file(str(deep))
    assert len(explorer.roots) == 2
    assert selected_path(explorer) == str(deep)
    assert notes_tab in window.tab_manager.tabs()


@needs_display
def test_removing_a_folder_and_turning_follow_off(window, tmp_path):
    files = make_tree(tmp_path)
    explorer = window.file_explorer
    window.open_file(str(files["work"]))
    window.open_file(str(files["notes"]))
    window.settings["explorer-follow"] = False
    try:
        explorer.remove_root(str(tmp_path / "home" / "notes"))
        assert explorer.roots == [str(tmp_path / "work")]
        window.open_file(str(files["ideas"]))  # outside: the tab opens, the sidebar stays put
        assert explorer.roots == [str(tmp_path / "work")]
        assert selected_path(explorer) is None
        assert window.file_manager.current_path == str(files["ideas"])
    finally:
        window.settings["explorer-follow"] = True


@needs_display
def test_folder_search_covers_every_folder_in_the_sidebar(window, tmp_path):
    files = make_tree(tmp_path)
    explorer = window.file_explorer
    explorer.set_roots([str(tmp_path / "work"), str(tmp_path / "home" / "notes")])
    explorer.add_root(str(tmp_path / "other"))
    bar = window.search_bar
    bar.show_dir_search()
    bar._dir_entry.set_text("needle")
    bar._on_dir_search()
    assert wait_for(lambda: getattr(bar._dir_results.get_row_at_index(2), "location", None))
    rows = [bar._dir_results.get_row_at_index(i) for i in range(3)]
    assert sorted(row.location[0] for row in rows) == sorted(str(p) for p in files.values())
    labels = sorted(row.get_child().get_first_child().get_text() for row in rows)
    assert labels == ["notes/README.md:2", "other/ideas.md:2", "work/README.md:2"]


@needs_display
def test_restoring_a_session_keeps_the_folders_as_they_were_left(app, tmp_path):
    from marker.utils import config_path
    from marker.window import MarkerWindow

    files = make_tree(tmp_path)
    if os.path.exists(config_path("session.json")):
        os.unlink(config_path("session.json"))
    first = MarkerWindow(application=app)
    first.present()
    first.open_file(str(files["work"]))
    first.open_file(str(files["notes"]))
    first.file_explorer.remove_root(str(tmp_path / "work"))  # the tab stays open
    first.close()
    iterate(0.2)

    second = MarkerWindow(application=app)
    try:
        second.present()
        second.restore_documents()
        iterate(0.2)
        assert second.file_explorer.roots == [str(tmp_path / "home" / "notes")]
        assert len(second.tab_manager.tabs()) == 2
    finally:
        second.close()
        iterate(0.1)
        os.unlink(config_path("session.json"))
