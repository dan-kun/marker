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
    tab = window.tab_manager.active_tab
    p = tab.preview
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


def test_links_do_not_navigate_the_preview(preview):
    uri = preview.get_webview().get_uri()
    render(preview, "[out](https://example.com)")
    js(preview, "document.querySelector('#content a').click(); return true")
    wait_for(lambda: False, timeout=0.5)  # give a navigation time to start
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
