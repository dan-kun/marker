"""Utility functions for Marker."""

from gi.repository import GLib


class Debouncer:
    """Calls a function after a delay, resetting the timer on each call."""

    def __init__(self, delay_ms: int, callback):
        self._delay_ms = delay_ms
        self._callback = callback
        self._source_id = None

    def trigger(self, *args, **kwargs):
        if self._source_id is not None:
            GLib.source_remove(self._source_id)

        def _fire():
            self._source_id = None
            self._callback(*args, **kwargs)
            return GLib.SOURCE_REMOVE

        self._source_id = GLib.timeout_add(self._delay_ms, _fire)

    def cancel(self):
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None
