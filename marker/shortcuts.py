"""Keyboard shortcuts: the single table behind the accelerators and the help window."""

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk


@dataclass(frozen=True)
class Shortcut:
    description: str
    accels: tuple[str, ...]
    action: str | None = None  # None: built into the editor, listed for reference
    label: str | None = None   # custom text for the help window


SHORTCUT_GROUPS: list[tuple[str, list[Shortcut]]] = [
    ("Files", [
        Shortcut("New document", ("<Ctrl>n",), "win.new-file"),
        Shortcut("New tab", ("<Ctrl>t",), "win.new-tab"),
        Shortcut("Open file", ("<Ctrl>o",), "win.open-file"),
        Shortcut("Save", ("<Ctrl>s",), "win.save-file"),
        Shortcut("Save as", ("<Ctrl><Shift>s",), "win.save-file-as"),
        Shortcut("Close tab", ("<Ctrl>w",), "win.close-file"),
    ]),
    ("Tabs", [
        Shortcut("Next tab", ("<Ctrl>Tab",), "win.next-tab"),
        Shortcut("Previous tab", ("<Ctrl><Shift>Tab",), "win.prev-tab"),
        Shortcut("Go to tab 1…9", ("<Ctrl>1",), label="Ctrl+1 … Ctrl+9"),
    ]),
    ("Editing", [
        Shortcut("Undo", ("<Ctrl>z",)),
        Shortcut("Redo", ("<Ctrl><Shift>z",)),
        Shortcut("Go to line", ("<Ctrl>g",), "win.goto-line"),
    ]),
    ("Formatting", [
        Shortcut("Bold", ("<Ctrl>b",), "win.format-bold"),
        Shortcut("Italic", ("<Ctrl>i",), "win.format-italic"),
        Shortcut("Inline code / code block", ("<Ctrl>grave",), "win.format-code"),
        Shortcut("Link", ("<Ctrl>l",), "win.format-link"),
    ]),
    ("Search", [
        Shortcut("Find in file", ("<Ctrl>f",), "win.find"),
        Shortcut("Find and replace", ("<Ctrl>h",), "win.find-replace"),
        Shortcut("Find in folder", ("<Ctrl><Shift>f",), "win.find-in-dir"),
        Shortcut("Next / previous match", ("Return",), label="Enter / Shift+Enter"),
        Shortcut("Close search", ("Escape",)),
    ]),
    ("View", [
        Shortcut("Toggle split view", ("<Ctrl>e",), "win.toggle-split"),
        Shortcut("Preview only", ("<Ctrl><Shift>p",), "win.preview-only"),
        Shortcut("Toggle sidebar", ("<Ctrl>backslash",), "win.show-sidebar"),
        Shortcut("Toggle minimap", ("<Ctrl>m",), "win.show-minimap"),
        Shortcut("Fullscreen", ("F11",), "win.fullscreen"),
        Shortcut("Zoom in", ("<Ctrl>plus", "<Ctrl>equal"), "win.zoom-in"),
        Shortcut("Zoom out", ("<Ctrl>minus",), "win.zoom-out"),
        Shortcut("Reset zoom", ("<Ctrl>0",), "win.zoom-reset"),
    ]),
    ("Application", [
        Shortcut("Preferences", ("<Ctrl>comma",), "win.preferences"),
        Shortcut("Keyboard shortcuts", ("<Ctrl>question",), "win.show-shortcuts"),
        Shortcut("Quit", ("<Ctrl>q",), "app.quit"),
    ]),
]


def iter_accels():
    """Yield (detailed action name, accels) for every bindable shortcut."""
    for _, shortcuts in SHORTCUT_GROUPS:
        for shortcut in shortcuts:
            if shortcut.action is not None:
                yield shortcut.action, list(shortcut.accels)
    for i in range(1, 10):
        yield f"win.goto-tab({i})", [f"<Ctrl>{i}"]


def accel_label(shortcut: Shortcut) -> str:
    if shortcut.label:
        return shortcut.label
    labels = []
    for accel in shortcut.accels[:1]:
        parsed = Gtk.accelerator_parse(accel)
        # PyGObject returns (key, mods) or (ok, key, mods) depending on version
        key, mods = parsed[-2], parsed[-1]
        labels.append(Gtk.accelerator_get_label(key, mods))
    return " / ".join(labels)


class ShortcutsWindow(Gtk.Window):
    def __init__(self, **kwargs):
        super().__init__(
            title="Keyboard Shortcuts",
            modal=True,
            default_width=460,
            default_height=560,
            resizable=True,
            **kwargs,
        )
        self.set_child(self._build_content())

    def _build_content(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_start(24)
        outer.set_margin_end(24)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)

        for i, (group_title, shortcuts) in enumerate(SHORTCUT_GROUPS):
            if i > 0:
                sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                sep.set_margin_top(8)
                sep.set_margin_bottom(8)
                outer.append(sep)

            heading = Gtk.Label(label=group_title, xalign=0)
            heading.add_css_class("heading")
            heading.set_margin_bottom(6)
            outer.append(heading)

            for shortcut in shortcuts:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                row.set_margin_top(2)
                row.set_margin_bottom(2)

                desc_label = Gtk.Label(label=shortcut.description, xalign=0)
                desc_label.set_hexpand(True)
                row.append(desc_label)

                keys = Gtk.Label(label=accel_label(shortcut), xalign=1)
                keys.add_css_class("monospace")
                keys.add_css_class("dim-label")
                keys.add_css_class("caption")
                row.append(keys)

                outer.append(row)

        scrolled.set_child(outer)
        return scrolled
