"""Recent files manager with JSON persistence."""

import json
import os
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject, GLib


MAX_STORED = 20
MENU_LIMIT = 10
SIDEBAR_LIMIT = 5


def _config_path() -> str:
    return os.path.join(GLib.get_user_config_dir(), "marker", "recents.json")


def format_relative_time(ts: float) -> str:
    delta = time.time() - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    if delta < 604800:
        return f"{int(delta / 86400)}d ago"
    return datetime.fromtimestamp(ts).strftime("%b %-d")


class RecentFilesManager(GObject.Object):
    """JSON-backed list of recently opened files, capped at MAX_STORED."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        try:
            with open(_config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._entries = data
        except (OSError, json.JSONDecodeError):
            self._entries = []

    def _save(self):
        path = _config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2)
        except OSError:
            pass

    def push(self, path: str):
        """Add path to the top of recents, deduplicating and trimming to MAX_STORED."""
        self._entries = [e for e in self._entries if e["path"] != path]
        self._entries.insert(0, {"path": path, "opened_at": time.time()})
        self._entries = self._entries[:MAX_STORED]
        self._save()
        self.emit("changed")

    def get_recents(self, limit: int = MAX_STORED) -> list[dict]:
        """Return up to `limit` entries, skipping files that no longer exist."""
        result = []
        for entry in self._entries:
            if os.path.isfile(entry["path"]):
                result.append(entry)
            if len(result) >= limit:
                break
        return result

    def clear(self):
        self._entries = []
        self._save()
        self.emit("changed")
