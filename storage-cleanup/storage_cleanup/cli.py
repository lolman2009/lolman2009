"""Command-line interface.

Examples:
    python -m storage_cleanup scan
    python -m storage_cleanup clean --categories temp cache
    python -m storage_cleanup clean --categories temp --really-delete
    python -m storage_cleanup large ~ --min-size 500MB
    python -m storage_cleanup duplicates ~/Pictures
    python -m storage_cleanup downloads --days 180
    python -m storage_cleanup gui
"""

import argparse
import sys
from pathlib import Path

from . import cleaner, locations, scanner
from .scanner import human_size


def print_disk_usage():
    total, used, free = scanner.disk_usage()
    pct = used / total * 100
    bar = "#" * int(pct / 5) + "-" * (20 - int(pct / 5))
    print(f"Disk: [{bar}] {pct:.0f}% used - {human_size(free)} free of {human_size(total)}\n")


def cmd_scan(args):
    print_disk_usage()
    grand_total = 0
    for key in args.categories:
        result = scanner.scan_category(key, min_age_days=args.min_age)
        grand_total += result.total_size
        note = f"  ({result.errors} unreadable)" if result.errors else ""
        print(f"  {result.label:<32} {len(result.files):>7} files  {human_size(result.total_size):>10}{note}")
    print(f"\n  {'Total reclaimable':<32} {'':>13}  {human_size(grand_total):>10}")
    print("\nRun 'clean' to preview deletion, then add --really-delete to free the space.")


def cmd_clean(args):
    dry_run = not args.really_delete
    if dry_run:
        print("DRY RUN - nothing will be deleted. Add --really-delete to actually clean.\n")
    elif not args.yes:
        answer = input(f"Permanently delete files in: {', '.join(args.categories)}? [y/N] ")
        if answer.strip().lower() != "y":
            print("Cancelled.")
            return

    freed = 0
    for key in args.categories:
        result = scanner.scan_category(key, min_age_days=args.min_age)
        report = cleaner.delete_files(result.files, dry_run=dry_run)
        if not dry_run:
            cleaner.remove_empty_dirs(locations.CATEGORIES[key][1](), dry_run=False)
        freed += report.freed
        verb = "Would delete" if dry_run else "Deleted"
        skipped = f", skipped {report.failed} in use/protected" if report.failed else ""
        print(f"  {result.label:<32} {verb} {report.deleted} files ({human_size(report.freed)}){skipped}")

    if "trash" in args.categories and locations.SYSTEM == "Windows":
        cleaner.empty_windows_recycle_bin(dry_run=dry_run)
        print("  Recycle Bin " + ("would be emptied" if dry_run else "emptied"))

    print(f"\n{'Would free' if dry_run else 'Freed'}: {human_size(freed)}")


def _print_entries(entries, show_age=False):
    import time
    for e in entries:
        age = f"  {int((time.time() - e.mtime) / 86400)}d old" if show_age else ""
        print(f"  {human_size(e.size):>10}{age}  {e.path}")


def cmd_large(args):
    min_size = scanner.parse_size(args.min_size)
    print(f"Files over {human_size(min_size)} in {args.path}:\n")
    entries = scanner.find_large_files(Path(args.path).expanduser(), min_size, args.limit)
    _print_entries(entries)
    if not entries:
        print("  None found.")


def cmd_downloads(args):
    entries = scanner.find_old_downloads(args.days)
    print(f"Downloads not modified in {args.days} days:\n")
    _print_entries(entries, show_age=True)
    print(f"\nTotal: {human_size(sum(e.size for e in entries))}")
    if entries and args.really_delete:
        if args.yes or input("Delete these files? [y/N] ").strip().lower() == "y":
            report = cleaner.delete_files(entries, dry_run=False)
            print(f"Deleted {report.deleted} files, freed {human_size(report.freed)}")


def cmd_duplicates(args):
    root = Path(args.path).expanduser()
    print(f"Looking for duplicate files in {root} (this can take a while)...\n")
    groups = scanner.find_duplicates(root, scanner.parse_size(args.min_size))
    wasted = 0
    for group in groups:
        keep, *copies = group
        wasted += keep.size * len(copies)
        print(f"{human_size(keep.size)} x {len(group)}")
        print(f"  keep:   {keep.path}")
        for c in copies:
            print(f"  copy:   {c.path}")
    print(f"\n{len(groups)} duplicate groups, {human_size(wasted)} wasted.")
    if groups and args.really_delete:
        if args.yes or input("Delete all copies (keeping the oldest of each)? [y/N] ").strip().lower() == "y":
            report = cleaner.delete_files([c for g in groups for c in g[1:]], dry_run=False)
            print(f"Deleted {report.deleted} files, freed {human_size(report.freed)}")


def cmd_gui(_args):
    try:
        from .gui import run
    except ImportError:
        sys.exit("The GUI needs Tkinter. On Linux: sudo apt install python3-tk\n"
                 "Or use the command line, e.g.: python -m storage_cleanup scan")
    run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="storage_cleanup",
                                     description="Find and remove junk files to free up disk space.")
    sub = parser.add_subparsers(dest="command", required=True)
    cats = list(locations.CATEGORIES)

    def add_common(p, delete=True):
        if delete:
            p.add_argument("--really-delete", action="store_true",
                           help="actually delete (default is a safe preview)")
            p.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")

    p = sub.add_parser("scan", help="show how much space each junk category uses")
    p.add_argument("--categories", nargs="+", choices=cats, default=cats)
    p.add_argument("--min-age", type=float, default=1, help="only count files older than N days (default 1)")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("clean", help="delete junk files (preview unless --really-delete)")
    p.add_argument("--categories", nargs="+", choices=cats, default=["temp", "cache"])
    p.add_argument("--min-age", type=float, default=1, help="only delete files older than N days (default 1)")
    add_common(p)
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser("large", help="list the biggest files in a folder")
    p.add_argument("path", nargs="?", default=str(Path.home()))
    p.add_argument("--min-size", default="100MB")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_large)

    p = sub.add_parser("downloads", help="list old files in your Downloads folder")
    p.add_argument("--days", type=int, default=90)
    add_common(p)
    p.set_defaults(func=cmd_downloads)

    p = sub.add_parser("duplicates", help="find identical files in a folder")
    p.add_argument("path", nargs="?", default=str(Path.home()))
    p.add_argument("--min-size", default="1KB")
    add_common(p)
    p.set_defaults(func=cmd_duplicates)

    p = sub.add_parser("gui", help="open the graphical app")
    p.set_defaults(func=cmd_gui)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
