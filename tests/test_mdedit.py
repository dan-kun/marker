"""Markdown editing rules (pure functions, no display needed)."""

import pytest

from marker.mdedit import list_enter, toggle_bullets, toggle_numbering, toggle_wrap


def apply(text: str, prefix: str, suffix: str | None = None) -> str:
    """Run toggle_wrap on text whose selection is marked with [ and ];
    returns the result with the new selection marked the same way."""
    start = text.index("[")
    end = text.index("]") - 1
    plain = text.replace("[", "").replace("]", "")
    edit = toggle_wrap(plain, start, end, prefix, suffix or prefix)
    result = plain[:edit.start] + edit.text + plain[edit.end:]
    return result[:edit.select_start] + "[" + result[edit.select_start:edit.select_end] + "]" \
        + result[edit.select_end:]


@pytest.mark.parametrize("before,marker,after", [
    # wrap, and select the inner text so that a second press unwraps
    ("a [word] b", "**", "a **[word]** b"),
    ("a **[word]** b", "**", "a [word] b"),
    # markers inside the selection
    ("a [**word**] b", "**", "a [word] b"),
    # empty selection: insert a pair, or remove an empty one
    ("a [] b", "**", "a **[]** b"),
    ("a **[]** b", "**", "a [] b"),
    # italic vs bold
    ("[word]", "*", "*[word]*"),
    ("*[word]*", "*", "[word]"),
    ("**[word]**", "*", "***[word]***"),    # bold text gains italic
    ("***[word]***", "*", "**[word]**"),    # bold-italic loses italic
    ("***[word]***", "**", "*[word]*"),     # bold-italic loses bold
    ("[**word**]", "*", "*[**word**]*"),
    # inline code
    ("run [ls -l]", "`", "run `[ls -l]`"),
    ("run `[ls -l]`", "`", "run [ls -l]"),
])
def test_toggle_wrap(before, marker, after):
    assert apply(before, marker) == after


def test_toggle_code_fence():
    fenced = apply("[a\nb]", "```\n", "\n```")
    assert fenced == "```\n[a\nb]\n```"
    assert apply(fenced, "```\n", "\n```") == "[a\nb]"


@pytest.mark.parametrize("line,expected", [
    ("- item", ("continue", "\n- ")),
    ("  * nested", ("continue", "\n  * ")),
    ("3. third", ("continue", "\n4. ")),
    ("9) nine", ("continue", "\n10) ")),
    ("- [x] done", ("continue", "\n- [ ] ")),
    ("- ", ("end", "- ")),
    ("  2. ", ("end", "  2. ")),
    ("- [ ] ", ("end", "- [ ] ")),
    ("plain text", None),
    ("**bold** start", None),
    ("-no space", None),
])
def test_list_enter_at_end_of_line(line, expected):
    assert list_enter(line, len(line)) == expected


def test_list_enter_before_the_marker_is_a_plain_newline():
    assert list_enter("- item", 0) is None
    assert list_enter("- item", 2) == ("continue", "\n- ")


def test_toggle_bullets_and_numbering():
    assert toggle_bullets(["a", "b"]) == ["- a", "- b"]
    assert toggle_bullets(["- a", "", "- b"]) == ["a", "", "b"]
    assert toggle_bullets(["- a", "b"]) == ["- - a", "- b"]  # mixed: add to all
    assert toggle_numbering(["a", "b", "c"]) == ["1. a", "2. b", "3. c"]
    assert toggle_numbering(["1. a", "2. b"]) == ["a", "b"]
    assert toggle_numbering(["  7) a"]) == ["  a"]
