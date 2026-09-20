"""Import-specific exceptions. Every one carries a message a user can act on."""

from __future__ import annotations


class RecwiseImportError(Exception):
    """Base class for all import failures."""


class FileTooLargeError(RecwiseImportError):
    """The input file exceeds the configured size cap."""


class UnsupportedFileTypeError(RecwiseImportError):
    """The input file's extension is not one we read."""


class MissingColumnError(RecwiseImportError):
    """A column named in the column mapping is not present in the file."""


class InvalidRowError(RecwiseImportError):
    """A specific row failed to parse; includes the row number (1-indexed, header excluded)."""

    def __init__(self, row_number: int, message: str) -> None:
        self.row_number = row_number
        super().__init__(f"row {row_number}: {message}")
