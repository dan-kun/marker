"""Logic that needs GObject but no display."""

import json

from marker.minimap import outline
from marker.recents import MAX_STORED, RecentFilesManager, format_relative_time
from marker.search import parse_grep_output
from marker.settings import DEFAULTS, Settings


def test_format_relative_time():
    now = 1_000_000.0
    assert format_relative_time(now - 5, now) == "just now"
    assert format_relative_time(now - 300, now) == "5m ago"
    assert format_relative_time(now - 7200, now) == "2h ago"
    assert format_relative_time(now - 3 * 86400, now) == "3d ago"


def test_recents_dedupes_caps_and_persists(tmp_path):
    store = tmp_path / "recents.json"
    files = []
    for i in range(MAX_STORED + 3):
        f = tmp_path / f"{i}.md"
        f.write_text("x")
        files.append(str(f))
    manager = RecentFilesManager(str(store))
    for f in files:
        manager.push(f)
    manager.push(files[-5])
    recents = manager.get_recents()
    assert len(recents) == MAX_STORED
    assert recents[0]["path"] == files[-5]
    assert [e["path"] for e in recents].count(files[-5]) == 1
    assert RecentFilesManager(str(store)).get_recents(limit=1)[0]["path"] == files[-5]


def test_recents_ignores_malformed_entries(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("x")
    store = tmp_path / "recents.json"
    store.write_text(json.dumps(["junk", {"path": 3}, {"path": str(good), "opened_at": 1.0}]))
    manager = RecentFilesManager(str(store))
    assert [e["path"] for e in manager.get_recents()] == [str(good)]


def test_settings_persist_and_validate(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(str(path))
    changed = []
    settings.connect("changed", lambda s, key: changed.append(key))
    settings["font-size"] = 16
    settings["font-size"] = 16  # unchanged: no signal
    assert changed == ["font-size"]
    assert Settings(str(path))["font-size"] == 16

    path.write_text(json.dumps({"font-size": "huge", "word-wrap": 1}))
    reloaded = Settings(str(path))
    assert reloaded["font-size"] == DEFAULTS["font-size"]
    assert reloaded["word-wrap"] == DEFAULTS["word-wrap"]


def test_parse_grep_output_handles_colons_and_bad_bytes():
    data = b"/tmp/a:b.md\x0012:hello: world\n/tmp/c.md\x003:caf\xe9\n\n"
    results, total = parse_grep_output(data)
    assert total == 2
    assert results[0] == ("/tmp/a:b.md", 12, "hello: world")
    assert results[1][2] == "caf�"


def test_parse_grep_output_limit():
    data = b"".join(b"/f.md\x00%d:x\n" % i for i in range(1, 11))
    results, total = parse_grep_output(data, limit=3)
    assert len(results) == 3 and total == 10


def test_outline_ignores_hashes_in_code_fences():
    lines = outline("# Title\ntext\n```\n# comment\n```\n## Sub")
    assert [h for h, _ in lines] == [True, False, False, False, False, True]
    assert max(w for _, w in lines) == 1.0
