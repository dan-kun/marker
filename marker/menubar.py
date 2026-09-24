"""Classic application menubar built from Gio.Menu."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk


def _section(*items) -> Gio.Menu:
    section = Gio.Menu()
    for label, action in items:
        section.append(label, action)
    return section


def _menu(*sections) -> Gio.Menu:
    menu = Gio.Menu()
    for section in sections:
        menu.append_section(None, section)
    return menu


def build_menubar(recents_menu: Gio.Menu) -> Gtk.PopoverMenuBar:
    """Build the menubar. recents_menu is shared with the header menu and
    filled in by the window."""
    root = Gio.Menu()

    open_recent = Gio.Menu()
    open_recent.append_submenu("Open Recent", recents_menu)
    root.append_submenu("File", _menu(
        _section(("New", "win.new-file"), ("New Tab", "win.new-tab"), ("Open…", "win.open-file")),
        open_recent,
        _section(("Save", "win.save-file"), ("Save As…", "win.save-file-as"),
                 ("Close Tab", "win.close-file")),
        _section(("Quit", "app.quit")),
    ))

    root.append_submenu("Edit", _menu(
        _section(("Find…", "win.find"), ("Find & Replace…", "win.find-replace"),
                 ("Find in Folder…", "win.find-in-dir"), ("Go to Line…", "win.goto-line")),
        _section(("Preferences", "win.preferences")),
    ))

    # Detailed "action::target" items render as radio buttons for the
    # stateful view-mode action; boolean actions render as check items.
    root.append_submenu("View", _menu(
        _section(("Editor Only", "win.view-mode::editor"), ("Split View", "win.view-mode::split"),
                 ("Preview Only", "win.view-mode::preview")),
        _section(("Sidebar", "win.show-sidebar"), ("Minimap", "win.show-minimap")),
        _section(("Zoom In", "win.zoom-in"), ("Zoom Out", "win.zoom-out"),
                 ("Reset Zoom", "win.zoom-reset"), ("Fullscreen", "win.fullscreen")),
    ))

    headings = Gio.Menu()
    for level in range(1, 7):
        item = Gio.MenuItem.new(f"Heading {level}", None)
        item.set_action_and_target_value("win.format-heading", GLib.Variant("i", level))
        headings.append_item(item)
    root.append_submenu("Format", _menu(
        _section(("Bold", "win.format-bold"), ("Italic", "win.format-italic"),
                 ("Code", "win.format-code"), ("Link", "win.format-link")),
        headings,
        _section(("Bullet List", "win.format-bullet-list"),
                 ("Numbered List", "win.format-numbered-list")),
    ))

    root.append_submenu("Help", _menu(
        _section(("Keyboard Shortcuts", "win.show-shortcuts"), ("About Marker", "app.about")),
    ))

    return Gtk.PopoverMenuBar.new_from_model(root)
