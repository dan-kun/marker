"""Window state remembered between runs: size, panels, open files."""

import json
import os

from .textio import write_text_file
from .utils import config_path

DEFAULTS = {
    "width": 1200,
    "height": 800,
    "maximized": False,
    "sidebar": True,
    "sidebar-width": 240,
    "minimap": True,
    "view-mode": "split",
    "zoom": 1.0,
    "folder": None,   # explorer root
    "files": [],      # open documents, in tab order
    "active": 0,      # index into "files" of the selected tab
}

_VIEW_MODES = ("editor", "split", "preview")


def _valid(key: str, value) -> bool:
    if key in ("width", "height", "sidebar-width"):
        return type(value) is int and 100 <= value <= 20000
    if key in ("maximized", "sidebar", "minimap"):
        return type(value) is bool
    if key == "view-mode":
        return value in _VIEW_MODES
    if key == "zoom":
        return type(value) in (int, float) and 0.5 <= value <= 3.0
    if key == "folder":
        return value is None or isinstance(value, str)
    if key == "files":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if key == "active":
        return type(value) is int and value >= 0
    return False


def load(path: str | None = None) -> dict:
    """The saved session, with defaults for anything missing or malformed."""
    state = dict(DEFAULTS)
    try:
        with open(path or config_path("session.json"), encoding="utf-8") as f:
            stored = json.load(f)
    except (OSError, ValueError):
        return state
    if isinstance(stored, dict):
        state.update({key: stored[key] for key in DEFAULTS if key in stored and _valid(key, stored[key])})
    return state


def save(state: dict, path: str | None = None):
    path = path or config_path("session.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text_file(path, json.dumps({key: state[key] for key in DEFAULTS}, indent=2) + "\n")
    except OSError:
        pass
