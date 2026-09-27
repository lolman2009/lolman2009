# Storage Cleanup

A cross-platform (Windows, macOS, Linux) app that finds and removes junk files to free up disk space.
Written in pure Python with no third-party dependencies. It has both a desktop GUI and a command line.

## Features

- **Disk usage overview:** free/used space for your main drive
- **Junk file cleanup:** temporary files, app & browser caches, Trash / Recycle Bin, old logs and crash dumps
- **Large file finder:** lists the biggest files in any folder
- **Duplicate finder:** groups identical files (size check first, then SHA-256), keeps the oldest copy
- **Old downloads:** files in `Downloads` you haven't touched in N days

## Safety

- The command line **previews by default**. Nothing is deleted unless you pass `--really-delete`, and it asks for confirmation unless you add `-y`.
- The GUI always asks for confirmation before deleting.
- Only files older than 1 day are cleaned by default (`--min-age`), so programs that are running don't lose files they're using.
- Symlinks are never followed, and system folders (`/etc`, `/usr`, `C:\Windows`, etc.) and your home folder itself are protected.
- Files that are locked or in use are skipped rather than causing an error.

## Requirements

Python 3.10+. On Linux, the GUI needs Tkinter (`sudo apt install python3-tk`).

## Usage

Run from inside the `storage-cleanup` folder:

```bash
# Open the GUI (also the default with no arguments)
python -m storage_cleanup gui

# See how much space each junk category uses
python -m storage_cleanup scan

# Preview a clean, then do it for real
python -m storage_cleanup clean --categories temp cache trash
python -m storage_cleanup clean --categories temp cache trash --really-delete

# Biggest files in your home folder
python -m storage_cleanup large ~ --min-size 500MB

# Duplicate files in Pictures (preview, then delete the copies)
python -m storage_cleanup duplicates ~/Pictures
python -m storage_cleanup duplicates ~/Pictures --really-delete

# Downloads older than 6 months
python -m storage_cleanup downloads --days 180
```

## Project layout

| File | Purpose |
|------|---------|
| `storage_cleanup/locations.py` | Where junk lives on each OS |
| `storage_cleanup/scanner.py` | Finds files (read-only): junk, large files, duplicates |
| `storage_cleanup/cleaner.py` | Deletes files, with dry-run and protected paths |
| `storage_cleanup/cli.py` | Command-line interface |
| `storage_cleanup/gui.py` | Tkinter desktop app |
| `tests/` | Unit tests |

## Running the tests

```bash
python -m unittest discover tests
```
