"""User preferences persisted as JSON in the config dir."""

import json
import os

from gi.repository import GObject

from .textio import write_text_file
from .utils import config_path

DEFAULTS = {
    "font-family": "Monospace",
    "font-size": 13,
    "tab-width": 4,
    "word-wrap": True,
    "line-numbers": True,
    "auto-save": False,
    "auto-save-delay": 30,
}


class Settings(GObject.Object):
    """Key/value preferences. Emits "changed"(key) after each update."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    _default: "Settings | None" = None

    def __init__(self, path: str | None = None):
        super().__init__()
        self._path = path or config_path("settings.json")
        self._data = dict(DEFAULTS)
        self._load()

    @classmethod
    def get_default(cls) -> "Settings":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                stored = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(stored, dict):
            return
        for key, default in DEFAULTS.items():
            value = stored.get(key)
            # bool is a subclass of int, so compare exact types
            if type(value) is type(default):
                self._data[key] = value

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            write_text_file(self._path, json.dumps(self._data, indent=2) + "\n")
        except OSError:
            pass

    def __getitem__(self, key: str):
        return self._data[key]

    def __setitem__(self, key: str, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        if self._data[key] == value:
            return
        self._data[key] = value
        self._save()
        self.emit("changed", key)
