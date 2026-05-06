"""Classic application menubar built from Gio.Menu."""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Gio, GLib


def build_menubar() -> Gtk.PopoverMenuBar:
    """Build and return the full application menubar."""
    root = Gio.Menu()

    # File menu
    file_menu = Gio.Menu()

    file_section1 = Gio.Menu()
    file_section1.append("New", "win.new-file")
    file_section1.append("New Tab", "win.new-tab")
    file_section1.append("Open…", "win.open-file")
    file_menu.append_section(None, file_section1)

    recents_menu = Gio.Menu()  # populated dynamically by window
    file_section2 = Gio.Menu()
    file_section2.append_submenu("Open Recent", recents_menu)
    file_menu.append_section(None, file_section2)

    file_section3 = Gio.Menu()
    file_section3.append("Save", "win.save-file")
    file_section3.append("Save As…", "win.save-file-as")
    file_section3.append("Close Tab", "win.close-file")
    file_menu.append_section(None, file_section3)

    file_section4 = Gio.Menu()
    file_section4.append("Quit", "app.quit")
    file_menu.append_section(None, file_section4)

    root.append_submenu("File", file_menu)

    # Edit menu
    edit_menu = Gio.Menu()

    edit_section1 = Gio.Menu()
    edit_section1.append("Find…", "win.find")
    edit_section1.append("Find & Replace…", "win.find-replace")
    edit_section1.append("Find in Folder…", "win.find-in-dir")
    edit_section1.append("Go to Line…", "win.goto-line")
    edit_menu.append_section(None, edit_section1)

    edit_section2 = Gio.Menu()
    edit_section2.append("Preferences", "win.preferences")
    edit_menu.append_section(None, edit_section2)

    root.append_submenu("Edit", edit_menu)

    # View menu
    view_menu = Gio.Menu()

    view_section1 = Gio.Menu()
    view_section1.append("Editor Only", "win.editor-only")
    view_section1.append("Split View", "win.toggle-split")
    view_section1.append("Preview Only", "win.preview-only")
    view_menu.append_section(None, view_section1)

    view_section2 = Gio.Menu()
    view_section2.append("Toggle Sidebar", "win.toggle-sidebar")
    view_section2.append("Toggle Minimap", "win.toggle-minimap")
    view_menu.append_section(None, view_section2)

    view_section3 = Gio.Menu()
    view_section3.append("Zoom In", "win.zoom-in")
    view_section3.append("Zoom Out", "win.zoom-out")
    view_section3.append("Reset Zoom", "win.zoom-reset")
    view_section3.append("Fullscreen", "win.fullscreen")
    view_menu.append_section(None, view_section3)

    root.append_submenu("View", view_menu)

    # Format menu
    format_menu = Gio.Menu()

    format_section1 = Gio.Menu()
    format_section1.append("Bold", "win.format-bold")
    format_section1.append("Italic", "win.format-italic")
    format_section1.append("Code", "win.format-code")
    format_section1.append("Link", "win.format-link")
    format_menu.append_section(None, format_section1)

    format_section2 = Gio.Menu()
    for i in range(1, 7):
        item = Gio.MenuItem.new(f"Heading {i}", None)
        item.set_action_and_target_value("win.format-heading", GLib.Variant("i", i))
        format_section2.append_item(item)
    format_menu.append_section(None, format_section2)

    format_section3 = Gio.Menu()
    format_section3.append("Bullet List", "win.format-bullet-list")
    format_section3.append("Numbered List", "win.format-numbered-list")
    format_menu.append_section(None, format_section3)

    root.append_submenu("Format", format_menu)

    # Help menu
    help_menu = Gio.Menu()
    help_menu.append("Keyboard Shortcuts", "win.show-shortcuts")
    help_menu.append("About Marker", "app.about")
    root.append_submenu("Help", help_menu)

    bar = Gtk.PopoverMenuBar.new_from_model(root)
    # Store recents_menu so window can populate it dynamically
    bar._recents_menu = recents_menu
    return bar
