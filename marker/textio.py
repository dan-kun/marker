"""Read and write text files without losing their encoding or line endings."""

import codecs
import os
import shutil
import tempfile
from dataclasses import dataclass

# Tried in order when a file is not valid UTF-8. latin-1 decodes any byte
# sequence, so the chain always succeeds and saving round-trips the bytes.
FALLBACK_ENCODINGS = ("cp1252", "latin-1")

ENCODING_NAMES = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8 BOM",
    "utf-16": "UTF-16",
    "cp1252": "Windows-1252",
    "latin-1": "ISO-8859-1",
}

NEWLINE_NAMES = {"\n": "LF", "\r\n": "CRLF", "\r": "CR"}


class BinaryFileError(ValueError):
    """Raised when a file looks like binary data rather than text."""


@dataclass
class TextFile:
    text: str       # always uses "\n" line endings
    encoding: str   # Python codec name used to decode the file
    newline: str    # dominant line ending in the file: "\n", "\r\n" or "\r"
    mtime_ns: int


def decode(data: bytes) -> tuple[str, str]:
    """Return (text, encoding) for raw file contents."""
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16"), "utf-16"
    if b"\x00" in data[:8192]:
        raise BinaryFileError("file contains NUL bytes")
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    for encoding in FALLBACK_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise AssertionError("latin-1 decodes every byte sequence")


def detect_newline(text: str) -> str:
    crlf = text.count("\r\n")
    cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf
    if crlf and crlf >= lf and crlf >= cr:
        return "\r\n"
    if cr > lf:
        return "\r"
    return "\n"


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_text_file(path: str) -> TextFile:
    with open(path, "rb") as f:
        data = f.read()
        mtime_ns = os.fstat(f.fileno()).st_mtime_ns
    text, encoding = decode(data)
    newline = detect_newline(text)
    return TextFile(normalize_newlines(text), encoding, newline, mtime_ns)


def _default_file_mode() -> int:
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def write_text_file(path: str, text: str, encoding: str = "utf-8", newline: str = "\n") -> int:
    """Atomically write text to path and return the new mtime (ns).

    The data goes to a temporary file in the same directory, which then
    replaces the target, so a failed write never truncates the original.
    Raises UnicodeEncodeError if text cannot be represented in encoding.
    """
    data = text.replace("\n", newline).encode(encoding)
    target = os.path.realpath(path)  # replace a symlink's target, not the link
    directory = os.path.dirname(target) or "."

    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=f".{os.path.basename(target)}.", suffix=".tmp"
        )
    except PermissionError:
        # Directory is read-only but the file itself may be writable.
        with open(target, "wb") as f:
            f.write(data)
        return os.stat(target).st_mtime_ns

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(target):
            shutil.copymode(target, tmp_path)
        else:
            os.chmod(tmp_path, _default_file_mode())
        os.replace(tmp_path, target)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return os.stat(target).st_mtime_ns
