"""Deleting files. Everything here respects dry_run so you can preview first."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import locations
from .scanner import FileEntry

# Never touch anything inside these, whatever a caller passes in.
PROTECTED = [Path(p) for p in ("/", "/bin", "/boot", "/etc", "/lib", "/sbin", "/usr",
                               "/System", "C:\\Windows", "C:\\Program Files")]


@dataclass
class CleanReport:
    deleted: int = 0
    freed: int = 0
    failed: int = 0


def is_protected(path: Path) -> bool:
    path = path.resolve()
    if path == locations.HOME.resolve():
        return True
    for p in PROTECTED:
        if path == p:
            return True
        if p != Path("/") and path.is_relative_to(p):
            return True
    return False


def delete_files(files: Iterable[FileEntry], dry_run: bool = True) -> CleanReport:
    report = CleanReport()
    for entry in files:
        if is_protected(entry.path):
            report.failed += 1
            continue
        if dry_run:
            report.deleted += 1
            report.freed += entry.size
            continue
        try:
            entry.path.unlink()
            report.deleted += 1
            report.freed += entry.size
        except OSError:
            # Locked or in use (common for temp files) - just skip it.
            report.failed += 1
    return report


def remove_empty_dirs(roots: Iterable[Path], dry_run: bool = True) -> int:
    """Remove now-empty sub-folders (never the root folders themselves)."""
    removed = 0
    for root in roots:
        # Deepest first so parents become empty after their children go.
        for d in sorted((p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()),
                        key=lambda p: len(p.parts), reverse=True):
            try:
                if not any(d.iterdir()):
                    if not dry_run:
                        d.rmdir()
                    removed += 1
            except OSError:
                pass
    return removed


def empty_windows_recycle_bin(dry_run: bool = True) -> bool:
    if locations.SYSTEM != "Windows":
        return False
    if dry_run:
        return True
    cmd = ["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"]
    return subprocess.run(cmd, capture_output=True).returncode == 0
