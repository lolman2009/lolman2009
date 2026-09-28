"""Known junk-file locations for each operating system.

Each category maps to a list of directories whose *contents* are safe to
remove (the directories themselves are kept).
"""

import os
import platform
import tempfile
from pathlib import Path

HOME = Path.home()
SYSTEM = platform.system()  # "Windows", "Darwin" (macOS) or "Linux"


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _existing(paths) -> list[Path]:
    """Drop missing entries and duplicates while keeping order."""
    seen, result = set(), []
    for p in paths:
        if p is None:
            continue
        p = p.expanduser()
        key = str(p.resolve()) if p.exists() else None
        if key and key not in seen and p.is_dir():
            seen.add(key)
            result.append(p)
    return result


def temp_dirs() -> list[Path]:
    paths = [Path(tempfile.gettempdir())]
    if SYSTEM == "Windows":
        paths += [_env_path("TEMP"), _env_path("TMP")]
    return _existing(paths)


def cache_dirs() -> list[Path]:
    if SYSTEM == "Windows":
        local = _env_path("LOCALAPPDATA")
        paths = []
        if local:
            paths += [
                local / "Microsoft" / "Windows" / "INetCache",
                local / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                local / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
                local / "Mozilla" / "Firefox" / "Profiles",
                local / "pip" / "Cache",
                local / "npm-cache",
            ]
        return _existing(paths)
    if SYSTEM == "Darwin":
        return _existing([HOME / "Library" / "Caches"])
    # Linux / other Unix
    xdg = _env_path("XDG_CACHE_HOME") or HOME / ".cache"
    return _existing([xdg])


def trash_dirs() -> list[Path]:
    if SYSTEM == "Windows":
        # The Recycle Bin is best emptied via the shell; see cleaner.empty_windows_recycle_bin
        return []
    if SYSTEM == "Darwin":
        return _existing([HOME / ".Trash"])
    data = _env_path("XDG_DATA_HOME") or HOME / ".local" / "share"
    return _existing([data / "Trash" / "files", data / "Trash" / "info"])


def log_dirs() -> list[Path]:
    if SYSTEM == "Windows":
        local = _env_path("LOCALAPPDATA")
        return _existing([local / "CrashDumps" if local else None])
    if SYSTEM == "Darwin":
        return _existing([HOME / "Library" / "Logs"])
    return _existing([HOME / ".local" / "state"])


def downloads_dir() -> Path:
    return HOME / "Downloads"


# Categories the user can pick from. Each entry: (label, function returning dirs, file filter)
CATEGORIES = {
    "temp": ("Temporary files", temp_dirs),
    "cache": ("Application & browser caches", cache_dirs),
    "trash": ("Trash / Recycle Bin", trash_dirs),
    "logs": ("Old log & crash files", log_dirs),
}
