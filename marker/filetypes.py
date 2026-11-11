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
    """Icon for a file in the sidebar. One icon for all: the per-type
    symbolic icons are missing from Adwaita, where they showed up as a
    mix of full-colour and "missing image" icons."""
    return "text-x-generic-symbolic"


# highlight.js language used to show a non-Markdown file in the preview
_PREVIEW_SYNTAX = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".sh": "bash",
    ".html": "xml", ".css": "css", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "ini", ".ini": "ini", ".cfg": "ini", ".conf": "ini",
}


def preview_syntax(path: str | None) -> str | None:
    """How the preview shows a file: None renders it as Markdown (untitled
    documents included); otherwise its text is shown as it is, highlighted
    as this highlight.js language ("plaintext" for none)."""
    if path is None or is_markdown(path):
        return None
    return _PREVIEW_SYNTAX.get(extension(path), "plaintext")
