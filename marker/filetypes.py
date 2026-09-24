"""File extensions Marker knows about, defined in one place."""

import os

MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown", ".mkd", ".mdown"})

TEXT_EXTENSIONS = frozenset({
    ".txt", ".rst", ".log", ".csv",
    ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf",
    ".py", ".js", ".ts", ".sh", ".html", ".css",
})

# Shown in the file explorer and searched by "Find in Folder"
SHOWN_EXTENSIONS = MARKDOWN_EXTENSIONS | TEXT_EXTENSIONS

OPEN_DIALOG_PATTERNS = tuple(f"*{ext}" for ext in sorted(MARKDOWN_EXTENSIONS | {".txt", ".rst"}))


def extension(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_markdown(path: str | None) -> bool:
    return path is not None and extension(path) in MARKDOWN_EXTENSIONS


def is_shown(name: str) -> bool:
    return extension(name) in SHOWN_EXTENSIONS


def icon_name(name: str) -> str:
    ext = extension(name)
    if ext in MARKDOWN_EXTENSIONS:
        return "text-x-markdown-symbolic"
    if ext == ".py":
        return "text-x-python-symbolic"
    if ext in {".json", ".yaml", ".yml", ".toml", ".sh", ".js", ".ts"}:
        return "text-x-script-symbolic"
    return "text-x-generic-symbolic"


def syntax_label(path: str | None) -> str:
    """Status-bar label. Untitled documents are edited as Markdown."""
    return "Markdown" if path is None or is_markdown(path) else "Plain Text"
