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
_NUMBERED = re.compile(r"^(\s*)\d+[.)]\s+")


def list_item_end(line: str) -> int | None:
    """Offset just past a list item's marker, or None if line is not one."""
    match = _LIST_ITEM.match(line)
    return match.end() if match else None


def list_enter(line: str, column: int) -> tuple[str, str] | None:
    """What Enter should do at `column` of `line`.

    ("continue", text): insert text, which starts the next list item.
    ("end", marker): the item is empty, so remove its marker to leave the list.
    None: not in a list item; let the editor handle the key.
    """
    match = _LIST_ITEM.match(line)
    if match is None or column < match.end():
        return None
    if not line[match.end():].strip():
        return "end", match.group(0)
    indent, bullet, number, delimiter, spacing, task = match.groups()
    marker = bullet if bullet else f"{int(number) + 1}{delimiter}"
    return "continue", f"\n{indent}{marker}{spacing}{'[ ] ' if task else ''}"


def toggle_bullets(lines: list[str]) -> list[str]:
    """Add "- " to lines, or remove it when every non-blank line has it."""
    content = [line for line in lines if line.strip()]
    if content and all(line.startswith("- ") for line in content):
        return [line[2:] if line.startswith("- ") else line for line in lines]
    return ["- " + line for line in lines]


def toggle_numbering(lines: list[str]) -> list[str]:
    """Number lines 1., 2., …, or remove the numbers when all have one."""
    content = [line for line in lines if line.strip()]
    if content and all(_NUMBERED.match(line) for line in content):
        return [_NUMBERED.sub(r"\1", line, count=1) for line in lines]
    return [f"{number}. {line}" for number, line in enumerate(lines, start=1)]
