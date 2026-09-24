import os
import stat

import pytest

from marker.textio import (
    BinaryFileError,
    decode,
    detect_newline,
    read_text_file,
    write_text_file,
)


def test_utf8_roundtrip(tmp_path):
    path = tmp_path / "a.md"
    path.write_bytes("héllo\nwörld\n".encode())
    tf = read_text_file(str(path))
    assert (tf.text, tf.encoding, tf.newline) == ("héllo\nwörld\n", "utf-8", "\n")


def test_non_utf8_is_preserved_byte_for_byte(tmp_path):
    original = "café – 10€\n".encode("cp1252")
    path = tmp_path / "legacy.txt"
    path.write_bytes(original)
    tf = read_text_file(str(path))
    assert tf.encoding == "cp1252"
    assert tf.text == "café – 10€\n"
    write_text_file(str(path), tf.text, tf.encoding, tf.newline)
    assert path.read_bytes() == original


def test_latin1_fallback_decodes_any_bytes():
    text, encoding = decode(b"\x81\x8d\xff")  # undefined in cp1252
    assert encoding == "latin-1"
    assert text.encode("latin-1") == b"\x81\x8d\xff"


def test_crlf_is_normalized_and_restored(tmp_path):
    path = tmp_path / "win.md"
    path.write_bytes(b"one\r\ntwo\r\n")
    tf = read_text_file(str(path))
    assert tf.text == "one\ntwo\n" and tf.newline == "\r\n"
    write_text_file(str(path), tf.text + "three\n", tf.encoding, tf.newline)
    assert path.read_bytes() == b"one\r\ntwo\r\nthree\r\n"


def test_bom_is_kept(tmp_path):
    path = tmp_path / "bom.md"
    path.write_bytes(b"\xef\xbb\xbfhi\n")
    tf = read_text_file(str(path))
    assert tf.encoding == "utf-8-sig" and tf.text == "hi\n"
    write_text_file(str(path), tf.text, tf.encoding)
    assert path.read_bytes() == b"\xef\xbb\xbfhi\n"


def test_binary_is_rejected(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    with pytest.raises(BinaryFileError):
        read_text_file(str(path))


@pytest.mark.parametrize("text,expected", [
    ("a\nb\n", "\n"), ("a\r\nb\r\n", "\r\n"), ("a\rb\r", "\r"), ("no newline", "\n"),
])
def test_detect_newline(text, expected):
    assert detect_newline(text) == expected


def test_write_keeps_permissions_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "script.sh"
    path.write_text("old")
    os.chmod(path, 0o750)
    write_text_file(str(path), "new")
    assert path.read_text() == "new"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o750
    assert os.listdir(tmp_path) == ["script.sh"]


def test_failed_encode_does_not_touch_file(tmp_path):
    path = tmp_path / "legacy.txt"
    path.write_bytes(b"original")
    with pytest.raises(UnicodeEncodeError):
        write_text_file(str(path), "emoji 🙂", "cp1252")
    assert path.read_bytes() == b"original"
    assert os.listdir(tmp_path) == ["legacy.txt"]


def test_write_through_symlink_updates_target(tmp_path):
    target = tmp_path / "real.md"
    target.write_text("old")
    link = tmp_path / "link.md"
    link.symlink_to(target)
    write_text_file(str(link), "new")
    assert link.is_symlink()
    assert target.read_text() == "new"
