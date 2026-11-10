"""The preview renders untrusted documents: check it cannot run their code."""

import base64
import json
import os

import pytest
from conftest import needs_display, wait_for

from marker.preview import WEB_DIR, MarkdownPreview

pytestmark = [
    needs_display,
    pytest.mark.skipif(
        not os.path.exists(os.path.join(WEB_DIR, "js", "purify.min.js")),
        reason="vendor assets missing (run scripts/fetch-deps.sh)",
    ),
]

# 1×1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def js(preview, script: str):
    """Evaluate an async JS function body and return its JSON-decoded result."""
    result = {}

    def done(webview, res):
        try:
            value = webview.call_async_javascript_function_finish(res)
            result["value"] = json.loads(value.to_json(0) or "null")
        except Exception as e:  # noqa: BLE001
            result["error"] = e

    preview.get_webview().call_async_javascript_function(
        script, -1, None, None, None, None, done
    )
    assert wait_for(lambda: result, timeout=10)
    if "error" in result:
        raise result["error"]
    return result["value"]


@pytest.fixture
def preview(window):
    p = window.preview
    assert wait_for(lambda: p._ready, timeout=15)
    return p


def render(preview, text):
    preview.render(text)
    assert wait_for(lambda: js(preview, "return document.getElementById('content').innerHTML.length > 0"))


def content_text(preview) -> str:
    return js(preview, "return document.getElementById('content').textContent.trim()")


def test_inline_script_and_event_handlers_are_stripped(preview):
    render(preview, '<img src="x" onerror="document.title=\'pwned\'">\n\n'
                    '<script>document.title="pwned2"</script>\n\n'
                    '[click](javascript:document.title="pwned3")')
    assert wait_for(lambda: js(preview, "return document.querySelector('#content img') !== null"))
    state = js(preview, """
        const c = document.getElementById('content');
        return {
          title: document.title,
          onerror: c.querySelector('img').getAttribute('onerror'),
          scripts: c.querySelectorAll('script').length,
          href: c.querySelector('a') ? c.querySelector('a').getAttribute('href') : null,
        };""")
    assert state["title"] == "Preview"
    assert state["onerror"] is None
    assert state["scripts"] == 0
    assert not (state["href"] or "").startswith("javascript:")


def test_page_cannot_read_local_files(preview):
    outcome = js(preview, """
        try { await fetch('file:///etc/hostname'); return 'read'; }
        catch (e) { return 'blocked'; }""")
    assert outcome == "blocked"


def test_relative_images_resolve_against_the_document(preview, tmp_path):
    (tmp_path / "pic.png").write_bytes(PNG)
    preview.set_base_dir(str(tmp_path))
    render(preview, "![alt](pic.png)")
    assert wait_for(lambda: js(preview, "const i = document.querySelector('#content img');"
                                        "return !!i && i.complete && i.naturalWidth === 1"))
    src = js(preview, "return document.querySelector('#content img').src")
    assert src == (tmp_path / "pic.png").as_uri()


def test_links_do_not_navigate_the_preview(preview, monkeypatch):
    launched = []
    monkeypatch.setattr(preview, "_open_link", launched.append)  # don't start a browser
    uri = preview.get_webview().get_uri()
    render(preview, "[out](https://example.com/page)")
    # Scripts run through the WebKit API count as user gestures
    js(preview, "document.querySelector('#content a').click(); return true")
    assert wait_for(lambda: launched, timeout=5)
    assert launched == ["https://example.com/page"]
    assert preview.get_webview().get_uri() == uri


def test_links_to_local_markdown_open_in_marker(preview, tmp_path):
    target = tmp_path / "other.md"
    target.write_text("# other")
    opened = []
    preview.connect("open-file", lambda p, path: opened.append(path))
    preview._open_link(target.as_uri())
    preview._open_link((tmp_path / "missing.md").as_uri())
    preview._open_link("javascript:alert(1)")
    assert opened == [str(target)]


def test_mermaid_math_and_code_render(preview):
    render(preview, "```mermaid\ngraph TD; A-->B\n```\n\n$E=mc^2$\n\n```python\nprint(1)\n```\n")
    assert wait_for(lambda: js(preview, """
        const c = document.getElementById('content');
        return !!c.querySelector('.mermaid svg') && !!c.querySelector('.katex')
               && !!c.querySelector('.hljs-built_in, .hljs-keyword, .hljs-number');"""), timeout=15)


def test_newer_render_wins(preview):
    preview.render("```mermaid\ngraph TD; A-->B\n```\n\nfirst")
    preview.render("second")
    assert wait_for(lambda: content_text(preview) == "second")
    # the slow mermaid render of "first" must not overwrite it afterwards
    wait_for(lambda: False, timeout=1)
    assert content_text(preview) == "second"


def test_dispose_disconnects_global_theme_handler(window):
    from gi.repository import Adw

    p = MarkdownPreview()
    handler = p._style_handler
    p.dispose()
    assert not Adw.StyleManager.get_default().handler_is_connected(handler)


def test_one_preview_follows_the_active_tab(preview, window, tmp_path):
    """Tabs share a single WebView: switching tabs re-points it."""
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("# Document A")
    b.write_text("# Document B")
    tab_a = window.open_file(str(a))
    assert wait_for(lambda: content_text(preview) == "Document A")
    tab_b = window.open_file(str(b))
    assert wait_for(lambda: content_text(preview) == "Document B")
    assert preview.get_parent() is tab_b.split_view

    window.tab_manager.select(tab_a)
    assert preview.get_parent() is tab_a.split_view
    assert wait_for(lambda: content_text(preview) == "Document A")

    # closing the active tab hands the preview to the tab that takes over
    window.tab_manager.close_active_tab()
    assert wait_for(lambda: preview.get_parent() is tab_b.split_view)
    assert wait_for(lambda: content_text(preview) == "Document B")


def test_preview_is_not_rendered_while_hidden(preview, window, tmp_path):
    rendered = []
    original = preview.render
    preview.render = lambda text, scroll=None: (rendered.append(text), original(text, scroll))[1]
    try:
        window.activate_action("win.editor-only", None)
        window.editor.set_text("# hidden")
        tab = window.tab_manager.new_tab()
        tab.split_view.set_mode("editor")
        tab.editor.set_text("# also hidden")
        wait_for(lambda: False, timeout=0.5)
        assert rendered == []
        tab.split_view.set_mode("split")
        assert rendered == ["# also hidden"]
    finally:
        del preview.render
        for t in window.tab_manager.tabs():
            t.editor.get_buffer().set_modified(False)


def test_preview_only_scroll_position_is_kept_per_tab(preview, window):
    first = window.tab_manager.active_tab
    first.editor.set_text("\n\n".join(f"paragraph {i}" for i in range(400)))
    first.split_view.set_mode("preview")
    assert wait_for(lambda: js(preview, "return document.documentElement.scrollHeight") > 3000)
    js(preview, "setScrollPercent(0.5); return true")

    window.tab_manager.new_tab()  # preview moves to the new, empty tab
    window.tab_manager.select(first)
    assert wait_for(lambda: abs(js(preview, "return getScrollPercent()") - 0.5) < 0.02)
    first.editor.get_buffer().set_modified(False)


def test_mermaid_is_loaded_on_demand_and_diagrams_are_cached(preview):
    render(preview, "plain text")
    assert js(preview, "return typeof window.mermaid") == "undefined"

    diagram = "```mermaid\ngraph TD; A-->B\n```\n"
    preview.render(diagram + "\none")
    has_diagram = "return !!document.querySelector('#content .mermaid svg')"
    assert wait_for(lambda: js(preview, has_diagram), timeout=15)
    renders = js(preview, "return _mermaidCounter")
    preview.render(diagram + "\ntwo")  # the diagram itself did not change
    assert wait_for(lambda: content_text(preview).endswith("two"))
    assert js(preview, has_diagram)
    assert js(preview, "return _mermaidCounter") == renders

    # a fenced mermaid block nested in another code block stays as code
    render(preview, "````md\n```mermaid\ngraph TD; A-->B\n```\n````\n")
    assert js(preview, "return document.querySelectorAll('#content .mermaid').length") == 0


def test_headings_get_ids_and_task_lists_get_checkboxes(preview):
    render(preview, "# Mi Título: instalación\n\n## Uso\n\n## Uso\n\n"
                    "- [ ] todo\n- [x] done\n- plain\n\n1. [X] numbered\n")
    ids = js(preview, "return [...document.querySelectorAll('#content h1, #content h2')].map(h => h.id)")
    assert ids == ["mi-título-instalación", "uso", "uso-1"]
    boxes = js(preview, """return [...document.querySelectorAll('#content input[type=checkbox]')]
        .map(b => [b.checked, b.disabled, b.closest('li').textContent.trim()])""")
    assert boxes == [[False, True, "todo"], [True, True, "done"], [True, True, "numbered"]]
    assert js(preview, "return document.querySelectorAll('#content li.task-list-item').length") == 3


def test_in_document_links_scroll_to_the_heading(preview):
    filler = "\n\n".join(f"paragraph {i}" for i in range(200))
    render(preview, f"[jump](#destino)\n\n{filler}\n\n## Destino\n\nend")
    uri = preview.get_webview().get_uri()
    js(preview, "document.querySelector('#content a').click(); return true")
    assert wait_for(lambda: js(preview, "return document.documentElement.scrollTop") > 1000)
    assert preview.get_webview().get_uri().split("#")[0] == uri.split("#")[0]


def test_scroll_follows_source_lines_not_percentages(preview):
    """A tall block (image, diagram) early in the document must not throw
    the two panes out of step."""
    lines = ["intro", "", '<div style="height:4000px">tall</div>', ""]
    lines += [line for i in range(40) for line in (f"paragraph {i}", "")]
    target_line = lines.index("paragraph 20")
    render(preview, "\n".join(lines))
    preview.scroll_to_line(target_line, 0.5)
    offset = """const el = [...document.querySelectorAll('#content p')]
        .find(p => p.textContent === 'paragraph 20'); return el.getBoundingClientRect().top;"""
    assert wait_for(lambda: abs(js(preview, offset)) < 2)
    # the ends of the document still line up
    preview.scroll_to_line(0, 0.0)
    assert wait_for(lambda: js(preview, "return document.documentElement.scrollTop") == 0)
    preview.scroll_to_line(target_line, 1.0)
    assert wait_for(lambda: abs(js(preview, "return getScrollPercent()") - 1) < 0.01)


def test_double_click_in_the_preview_reports_the_source_line(preview, window):
    window.editor.set_text("one\n\ntwo\n\nthree\n")
    assert wait_for(lambda: content_text(preview).endswith("three"))
    js(preview, """const p = [...document.querySelectorAll('#content p')]
            .find(p => p.textContent === 'three');
        p.dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); return true;""")
    assert wait_for(lambda: window.editor.get_cursor_position() == (5, 1))
    window.editor.get_buffer().set_modified(False)
