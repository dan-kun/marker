"""Recent files manager with JSON persistence."""

import json
import os
import time
from datetime import datetime

from gi.repository import GObject

from .textio import write_text_file
from .utils import config_path

MAX_STORED = 20
MENU_LIMIT = 10
SIDEBAR_LIMIT = 5


def format_relative_time(ts: float, now: float | None = None) -> str:
    delta = (time.time() if now is None else now) - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    if delta < 604800:
        return f"{int(delta / 86400)}d ago"
    date = datetime.fromtimestamp(ts)
    return f"{date:%b} {date.day}"


def _valid_entry(entry) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and isinstance(entry.get("opened_at"), (int, float))
    )


class RecentFilesManager(GObject.Object):
    """JSON-backed list of recently opened files, capped at MAX_STORED."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, path: str | None = None):
        super().__init__()
        self._path = path or config_path("recents.json")
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(data, list):
            self._entries = [e for e in data if _valid_entry(e)][:MAX_STORED]

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            write_text_file(self._path, json.dumps(self._entries, indent=2) + "\n")
        except OSError:
            pass

    def push(self, path: str):
        """Add path to the top of recents, deduplicating and trimming to MAX_STORED."""
        path = os.path.abspath(path)
        self._entries = [e for e in self._entries if e["path"] != path]
        self._entries.insert(0, {"path": path, "opened_at": time.time()})
        del self._entries[MAX_STORED:]
        self._save()
        self.emit("changed")

    def get_recents(self, limit: int = MAX_STORED) -> list[dict]:
        """Return up to `limit` entries, skipping files that no longer exist."""
        result = []
        for entry in self._entries:
            if len(result) >= limit:
                break
            if os.path.isfile(entry["path"]):
                result.append(entry)
        return result

    def clear(self):
        self._entries = []
        self._save()
        self.emit("changed")
