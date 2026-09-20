"""Handling browser-uploaded ledger/bank files.

Only ever writes to a filename this module chooses (never the client's
supplied filename) -- so no attacker-controlled string can become part of
a filesystem path, per CLAUDE.md's "never build file paths from user
input without resolving and checking they stay inside the intended
directory" rule. The client's filename is used only to read its
extension, which is checked against a fixed allowlist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

ALLOWED_SUFFIXES = {".csv", ".xlsx"}


class UnsupportedUploadError(Exception):
    """The uploaded file's extension is not one recwise reads."""


class SavesTo(Protocol):
    def save(self, dst: Path) -> None: ...


def upload_suffix(client_filename: str) -> str:
    """Extract and validate the extension from a client-supplied filename.

    Raises UnsupportedUploadError for anything outside ALLOWED_SUFFIXES.
    The filename is never used to build a path -- only this validated
    extension is, and only appended to a caller-chosen literal name.
    """
    suffix = Path(client_filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UnsupportedUploadError(
            f"unsupported file type {suffix!r}; expected one of {sorted(ALLOWED_SUFFIXES)}"
        )
    return suffix


def save_upload(upload_dir: Path, fixed_name: str, suffix: str, upload: SavesTo) -> Path:
    """Save an uploaded file under a name this module controls.

    `fixed_name` must be a caller-chosen literal ("ledger" or "bank"),
    never derived from user input, so the resulting path always resolves
    inside `upload_dir`. Checked explicitly anyway as defense in depth.
    """
    upload_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = upload_dir.resolve()
    dest = (resolved_dir / f"{fixed_name}{suffix}").resolve()
    if dest.parent != resolved_dir:
        raise UnsupportedUploadError("resolved upload path escaped the upload directory")
    upload.save(dest)
    return dest
