"""Portable, validated `.synopsis` course archive adapter."""

from .archive import (
    ArchiveDiagnostic,
    ArchiveError,
    ArchiveLimits,
    ExportResult,
    export_course,
    import_course,
)

__all__ = ["ArchiveDiagnostic", "ArchiveError", "ArchiveLimits", "ExportResult", "export_course", "import_course"]
