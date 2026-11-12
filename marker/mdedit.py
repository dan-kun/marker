"""Markdown editing rules as pure functions on strings.

The editor widget applies the results to its text buffer; keeping the rules
here makes them testable without a display.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Edit:
    """Replace text[start:end] with `text`, then select [select_start, select_end)."""

    start: int
    end: int
    text: str
    select_start: int
    select_end: int


def _leading(text: str, char: str) -> int:
    return len(text) - len(text.lstrip(char))


def _trailing(text: str, char: str) -> int:
    return len(text) - len(text.rstrip(char))


def _marker_runs_match(prefix: str, lead: int, trail: int) -> bool:
    """For * markers, tell *italic* (1 or 3 stars) from **bold** (2 or more)."""
    if prefix == "*":
        return lead in (1, 3) and trail in (1, 3)
    if prefix == "**":
        return lead >= 2 and trail >= 2
    return True


def is_wrapped(text: str, prefix: str, suffix: str) -> bool:
    """Whether text is already enclosed in prefix…suffix."""
    if len(text) < len(prefix) + len(suffix):
        return False
    if not (text.startswith(prefix) and text.endswith(suffix)):
        return False
    if set(prefix) == {"*"}:
        return _marker_runs_match(prefix, _leading(text, "*"), _trailing(text, "*"))
    return True


def toggle_wrap(text: str, start: int, end: int, prefix: str, suffix: str) -> Edit:
    """Add prefix/suffix around text[start:end], or remove them if present.

    The markers count as present when they are inside the selection
    ("**word**" selected) or just outside it ("word" selected in "**word**").
    With an empty selection an empty pair is inserted, or removed when the
    cursor already sits inside one.
    """
    selected = text[start:end]
    before, after = text[:start], text[end:]
    p, s = len(prefix), len(suffix)

    outside = before.endswith(prefix) and after.startswith(suffix)
    if outside and set(prefix) == {"*"}:
        outside = _marker_runs_match(prefix, _trailing(before, "*"), _leading(after, "*"))

    if start == end:
        if outside:
            return Edit(start - p, end + s, "", start - p, start - p)
        return Edit(start, end, prefix + suffix, start + p, start + p)

    if is_wrapped(selected, prefix, suffix):
        inner = selected[p:len(selected) - s]
        return Edit(start, end, inner, start, start + len(inner))
    if outside:
        return Edit(start - p, end + s, selected, start - p, start - p + len(selected))
    return Edit(start, end, prefix + selected + suffix, start + p, start + p + len(selected))


# indent, bullet | number + delimiter, spacing, optional task checkbox
_LIST_ITEM = re.compile(r"^(\s*)(?:([-*+])|(\d+)([.)]))(\s+)(\[[ xX]\]\s+)?")
_BULLET = re.compile(r"^(\s*)[-*+]\s+")
_NUMBERED = re.compile(r"^(\s*)\d+[.)]\s+")
_THEMATIC_BREAK = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")  # "* * *", "---"
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

# Spaces that nest a list item one level. Four puts the item inside its
# parent for bullets and for numbers up to "99.", whatever the tab width.
LIST_INDENT = 4


def list_item_end(line: str) -> int | None:
    """Offset just past a list item's marker, or None if line is not one."""
    if _THEMATIC_BREAK.match(line):
        return None
    match = _LIST_ITEM.match(line)
    return match.end() if match else None


def outdent_width(line: str) -> int:
    """How many leading characters to remove to move line out one level."""
    if line.startswith("\t"):
        return 1
    return min(len(line) - len(line.lstrip(" ")), LIST_INDENT)


def in_code_fence(lines_before: list[str]) -> bool:
    """Whether the line after lines_before is inside a ``` or ~~~ block."""
    fence = None
    for line in lines_before:
        match = _FENCE.match(line)
        if match is None:
            continue
        marker = match.group(1)
        if fence is None:
            fence = marker
        elif marker[0] == fence[0] and len(marker) >= len(fence) and not line[match.end():].strip():
            fence = None
    return fence is not None


def list_enter(line: str, column: int) -> tuple[str, str] | None:
    """What Enter should do at `column` of `line`.

    ("continue", text): insert text, which starts the next list item.
    ("end", marker): the item is empty, so remove its marker to leave the list.
    ("outdent", indent): the empty item is nested, so remove this much of its
        indentation to move it out one level.
    None: not in a list item; let the editor handle the key.
    """
    match = _LIST_ITEM.match(line)
    if match is None or column < match.end() or _THEMATIC_BREAK.match(line):
        return None
    indent, bullet, number, delimiter, spacing, task = match.groups()
    if not line[match.end():].strip():
        width = outdent_width(line)
        return ("outdent", line[:width]) if width else ("end", match.group(0))
    marker = bullet if bullet else f"{int(number) + 1}{delimiter}"
    return "continue", f"\n{indent}{marker}{spacing}{'[ ] ' if task else ''}"


def _split_marker(line: str) -> tuple[str, str]:
    """(indentation, text) of a line, without its bullet or number."""
    for pattern in (_BULLET, _NUMBERED):
        match = pattern.match(line)
        if match and not _THEMATIC_BREAK.match(line):
            return match.group(1), line[match.end():]
    text = line.lstrip()
    return line[:len(line) - len(text)], text


def toggle_bullets(lines: list[str]) -> list[str]:
    """Make the lines a bullet list, or plain text again when every one of
    them already is a bullet. Blank lines are left alone; numbers become
    bullets."""
    content = [line for line in lines if line.strip()]
    if not content:
        return ["- " + line for line in lines]  # on an empty line: start a list
    if all(_BULLET.match(line) for line in content):
        return [_BULLET.sub(r"\1", line, count=1) for line in lines]
    result = []
    for line in lines:
        if line.strip() and not _BULLET.match(line):
            indent, text = _split_marker(line)
            line = f"{indent}- {text}"
        result.append(line)
    return result


def toggle_numbering(lines: list[str]) -> list[str]:
    """Number the lines 1., 2., …, or remove the numbers when all have one.
    Blank lines are left alone and not counted; bullets become numbers."""
    content = [line for line in lines if line.strip()]
    if not content:
        return [f"{number}. {line}" for number, line in enumerate(lines, start=1)]
    if all(_NUMBERED.match(line) for line in content):
        return [_NUMBERED.sub(r"\1", line, count=1) for line in lines]
    result, number = [], 0
    for line in lines:
        if line.strip():
            number += 1
            indent, text = _split_marker(line)
            line = f"{indent}{number}. {text}"
        result.append(line)
    return result
