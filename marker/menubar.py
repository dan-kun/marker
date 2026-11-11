"""Classic application menubar built from Gio.Menu."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gio, GLib, Gtk


def _section(*items) -> Gio.Menu:
    """A menu section from (label, action) or (label, action, accelerator)
    tuples. Shortcuts that only work inside the editor are not registered
    with the application, so the menu is told what to display for them."""
    section = Gio.Menu()
    for label, action, *accel in items:
        item = Gio.MenuItem.new(label, action)
        if accel:
            item.set_attribute_value("accel", GLib.Variant("s", accel[0]))
        section.append_item(item)
    return section


def _menu(*sections) -> Gio.Menu:
    menu = Gio.Menu()
    for section in sections:
        menu.append_section(None, section)
    return menu


def build_menubar(recents_menu: Gio.Menu) -> Gtk.PopoverMenuBar:
    """Build the menubar. recents_menu is shared with the header menu and
    filled in by the window. Underscores mark the Alt+letter mnemonics."""
    root = Gio.Menu()

    open_recent = Gio.Menu()
    open_recent.append_submenu("Open _Recent", recents_menu)
    root.append_submenu("_File", _menu(
        _section(("_New", "win.new-file"), ("New _Tab", "win.new-tab"), ("_Open…", "win.open-file")),
        open_recent,
        _section(("_Save", "win.save-file"), ("Save _As…", "win.save-file-as"),
                 ("Reload from _Disk", "win.reload"), ("_Close Tab", "win.close-file")),
        _section(("_Quit", "app.quit")),
    ))

    root.append_submenu("_Edit", _menu(
        _section(("_Undo", "win.undo", "<Ctrl>z"), ("Re_do", "win.redo", "<Ctrl><Shift>z")),
        _section(("Cu_t", "win.cut", "<Ctrl>x"), ("_Copy", "win.copy", "<Ctrl>c"),
                 ("_Paste", "win.paste", "<Ctrl>v"), ("Select _All", "win.select-all", "<Ctrl>a")),
        _section(("_Find…", "win.find"), ("Find and _Replace…", "win.find-replace"),
                 ("Find in F_older…", "win.find-in-dir"), ("Go to _Line…", "win.goto-line")),
        _section(("Prefere_nces", "win.preferences")),
    ))

    # Detailed "action::target" items render as radio buttons for the
    # stateful view-mode action; boolean actions render as check items.
    root.append_submenu("_View", _menu(
        _section(("_Editor Only", "win.view-mode::editor"), ("_Split View", "win.view-mode::split"),
                 ("_Preview Only", "win.view-mode::preview")),
        _section(("Side_bar", "win.show-sidebar"), ("_Minimap", "win.show-minimap")),
        _section(("Zoom _In", "win.zoom-in"), ("Zoom _Out", "win.zoom-out"),
                 ("_Reset Zoom", "win.zoom-reset"), ("_Fullscreen", "win.fullscreen")),
    ))

    headings = Gio.Menu()
    for level in range(1, 7):
        item = Gio.MenuItem.new(f"Heading _{level}", None)
        item.set_action_and_target_value("win.format-heading", GLib.Variant("i", level))
        headings.append_item(item)
    root.append_submenu("F_ormat", _menu(
        _section(("_Bold", "win.format-bold", "<Ctrl>b"), ("_Italic", "win.format-italic", "<Ctrl>i"),
                 ("_Code", "win.format-code", "<Ctrl>grave"), ("_Link", "win.format-link", "<Ctrl>l")),
        headings,
        _section(("B_ullet List", "win.format-bullet-list"),
                 ("_Numbered List", "win.format-numbered-list")),
    ))

    root.append_submenu("_Help", _menu(
        _section(("_Keyboard Shortcuts", "win.show-shortcuts"), ("_About Marker", "app.about")),
    ))

    return Gtk.PopoverMenuBar.new_from_model(root)
