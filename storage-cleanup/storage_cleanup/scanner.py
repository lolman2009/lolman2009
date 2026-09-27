"""Scanning: work out what could be cleaned, without deleting anything."""

import hashlib
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from . import locations

LOG_EXTENSIONS = {".log", ".old", ".dmp", ".crash", ".gz"}


@dataclass
class FileEntry:
    path: Path
    size: int
    mtime: float


@dataclass
class ScanResult:
    category: str
    label: str
    files: list[FileEntry] = field(default_factory=list)
    errors: int = 0

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024 or unit == "TB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{int(num_bytes)} B"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def parse_size(text: str) -> int:
    """Turn '500MB', '1.5 GB' or '2048' into a number of bytes."""
    text = text.strip().upper().replace(" ", "")
    units = {"TB": 1024**4, "GB": 1024**3, "MB": 1024**2, "KB": 1024, "B": 1}
    for unit, factor in units.items():
        if text.endswith(unit):
            return int(float(text[: -len(unit)]) * factor)
    return int(float(text))


def walk_files(roots: Iterable[Path], on_error: Callable[[], None] | None = None):
    """Yield FileEntry for every regular file under the given roots.

    Symlinks are never followed so we can't wander outside a folder.
    """
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False,
                                                    onerror=lambda e: on_error and on_error()):
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    st = path.lstat()
                except OSError:
                    if on_error:
                        on_error()
                    continue
                if path.is_symlink():
                    continue
                yield FileEntry(path, st.st_size, st.st_mtime)


def scan_category(key: str, min_age_days: float = 0) -> ScanResult:
    """Scan one junk category (see locations.CATEGORIES)."""
    label, dirs_func = locations.CATEGORIES[key]
    result = ScanResult(key, label)
    cutoff = time.time() - min_age_days * 86400

    def count_error():
        result.errors += 1

    for entry in walk_files(dirs_func(), on_error=count_error):
        if entry.mtime > cutoff:
            continue  # recently used; probably still needed
        if key == "logs" and entry.path.suffix.lower() not in LOG_EXTENSIONS:
            continue
        result.files.append(entry)
    return result


def find_large_files(root: Path, min_size: int, limit: int = 50) -> list[FileEntry]:
    """Largest files under root that are at least min_size bytes."""
    found = [e for e in walk_files([root]) if e.size >= min_size]
    found.sort(key=lambda e: e.size, reverse=True)
    return found[:limit]


def find_old_downloads(days: int = 90) -> list[FileEntry]:
    folder = locations.downloads_dir()
    if not folder.is_dir():
        return []
    cutoff = time.time() - days * 86400
    return sorted((e for e in walk_files([folder]) if e.mtime < cutoff),
                  key=lambda e: e.size, reverse=True)


def _file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def find_duplicates(root: Path, min_size: int = 1024) -> list[list[FileEntry]]:
    """Groups of identical files. The first file in each group is the oldest
    (the one we'd keep); the rest are the copies.

    Files are first grouped by size, and only same-size files get hashed,
    which keeps this fast on big folders.
    """
    by_size: dict[int, list[FileEntry]] = defaultdict(list)
    for entry in walk_files([root]):
        if entry.size >= min_size:
            by_size[entry.size].append(entry)

    groups = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_hash: dict[str, list[FileEntry]] = defaultdict(list)
        for entry in same_size:
            digest = _file_hash(entry.path)
            if digest:
                by_hash[digest].append(entry)
        for dupes in by_hash.values():
            if len(dupes) > 1:
                dupes.sort(key=lambda e: e.mtime)
                groups.append(dupes)
    groups.sort(key=lambda g: g[0].size * (len(g) - 1), reverse=True)
    return groups


def disk_usage(path: Path | str = None):
    """(total, used, free) bytes for the drive containing path."""
    import shutil
    return shutil.disk_usage(path or Path.home().anchor or "/")
