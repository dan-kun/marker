"""Utility functions for Marker."""

import os

from gi.repository import GLib


def config_path(filename: str) -> str:
    """Path of a file in Marker's config dir (~/.config/marker by default)."""
    return os.path.join(GLib.get_user_config_dir(), "marker", filename)


class Debouncer:
    """Calls a function after a delay, resetting the timer on each call."""

    def __init__(self, delay_ms: int, callback):
        self.delay_ms = delay_ms
        self._callback = callback
        self._source_id = None

    @property
    def pending(self) -> bool:
        return self._source_id is not None

    def trigger(self, *args, **kwargs):
        self.cancel()

        def _fire():
            self._source_id = None
            self._callback(*args, **kwargs)
            return GLib.SOURCE_REMOVE

        self._source_id = GLib.timeout_add(self.delay_ms, _fire)

    def flush(self, *args, **kwargs):
        """Run the callback now if a call is pending."""
        if self._source_id is not None:
            self.cancel()
            self._callback(*args, **kwargs)

    def cancel(self):
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None
