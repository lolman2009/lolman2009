"""Tkinter desktop app. Tkinter ships with Python, so there's nothing to install."""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import cleaner, locations, scanner
from .scanner import human_size


class CleanupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Storage Cleanup")
        self.geometry("820x560")
        self.minsize(640, 420)

        self.results: dict[str, scanner.ScanResult] = {}
        self.extra_files: list[scanner.FileEntry] = []  # large/duplicate files picked by the user
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        self._build_disk_bar()
        self._build_notebook()
        self._build_status()
        self.refresh_disk_bar()
        self.after(100, self._poll_events)

    # ---------- layout ----------
    def _build_disk_bar(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="x")
        self.disk_label = ttk.Label(frame, font=("TkDefaultFont", 11, "bold"))
        self.disk_label.pack(anchor="w")
        self.disk_bar = ttk.Progressbar(frame, maximum=100)
        self.disk_bar.pack(fill="x", pady=(4, 0))

    def _build_notebook(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10)
        nb.add(self._build_junk_tab(nb), text="Junk files")
        nb.add(self._build_finder_tab(nb), text="Large & duplicate files")

    def _build_junk_tab(self, parent):
        tab = ttk.Frame(parent, padding=10)
        self.cat_vars = {}
        self.cat_labels = {}
        for key, (label, _) in locations.CATEGORIES.items():
            row = ttk.Frame(tab)
            row.pack(fill="x", pady=3)
            var = tk.BooleanVar(value=key in ("temp", "cache"))
            ttk.Checkbutton(row, text=label, variable=var).pack(side="left")
            size_label = ttk.Label(row, text="not scanned", foreground="gray")
            size_label.pack(side="right")
            self.cat_vars[key] = var
            self.cat_labels[key] = size_label

        age_row = ttk.Frame(tab)
        age_row.pack(fill="x", pady=(12, 3))
        ttk.Label(age_row, text="Only files older than (days):").pack(side="left")
        self.min_age = tk.StringVar(value="1")
        ttk.Spinbox(age_row, from_=0, to=365, width=5, textvariable=self.min_age).pack(side="left", padx=5)

        buttons = ttk.Frame(tab)
        buttons.pack(fill="x", pady=12)
        self.scan_btn = ttk.Button(buttons, text="Scan", command=self.start_scan)
        self.scan_btn.pack(side="left")
        self.clean_btn = ttk.Button(buttons, text="Clean selected", command=self.start_clean, state="disabled")
        self.clean_btn.pack(side="left", padx=8)
        self.total_label = ttk.Label(buttons, font=("TkDefaultFont", 10, "bold"))
        self.total_label.pack(side="right")
        return tab

    def _build_finder_tab(self, parent):
        tab = ttk.Frame(parent, padding=10)
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.folder = tk.StringVar(value=str(Path.home()))
        ttk.Entry(top, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Browse...", command=self._browse).pack(side="left", padx=4)
        ttk.Button(top, text="Find large (>100 MB)", command=self.start_large).pack(side="left", padx=4)
        ttk.Button(top, text="Find duplicates", command=self.start_duplicates).pack(side="left")

        cols = ("size", "path")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("size", text="Size")
        self.tree.heading("path", text="Path")
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.column("path", width=600)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, pady=8)
        scroll.pack(side="left", fill="y", pady=8)

        side = ttk.Frame(tab)
        side.pack(side="left", fill="y", padx=(8, 0), pady=8)
        ttk.Label(side, text="Select rows, then:", wraplength=120).pack(anchor="w")
        ttk.Button(side, text="Delete selected", command=self.delete_selected).pack(fill="x", pady=4)
        return tab

    def _build_status(self):
        self.status = tk.StringVar(value="Ready. Click Scan to see how much space you can free.")
        ttk.Label(self, textvariable=self.status, relief="sunken", padding=4).pack(fill="x", side="bottom")

    # ---------- helpers ----------
    def refresh_disk_bar(self):
        total, used, free = scanner.disk_usage()
        pct = used / total * 100
        self.disk_bar["value"] = pct
        self.disk_label["text"] = f"{human_size(free)} free of {human_size(total)} ({pct:.0f}% used)"

    def _browse(self):
        folder = filedialog.askdirectory(initialdir=self.folder.get())
        if folder:
            self.folder.set(folder)

    def _run_in_background(self, message, func):
        """Run func in a thread; it posts results to self.events for the UI thread."""
        if self.busy:
            return
        self.busy = True
        self.status.set(message)
        self.scan_btn["state"] = "disabled"

        def worker():
            try:
                func()
            except Exception as exc:  # show any unexpected error rather than crash silently
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self):
        # Tkinter isn't thread-safe, so worker threads talk to the UI via this queue.
        try:
            while True:
                kind, payload = self.events.get_nowait()
                getattr(self, f"_on_{kind}")(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _selected_categories(self):
        return [k for k, v in self.cat_vars.items() if v.get()]

    def _min_age(self):
        try:
            return max(0.0, float(self.min_age.get()))
        except ValueError:
            return 1.0

    # ---------- junk tab ----------
    def start_scan(self):
        age = self._min_age()

        def job():
            for key in locations.CATEGORIES:
                self.events.put(("progress", f"Scanning {locations.CATEGORIES[key][0]}..."))
                self.events.put(("scanned", scanner.scan_category(key, min_age_days=age)))

        self._run_in_background("Scanning...", job)

    def start_clean(self):
        keys = [k for k in self._selected_categories() if k in self.results]
        if not keys:
            messagebox.showinfo("Nothing selected", "Tick at least one scanned category.")
            return
        total = sum(self.results[k].total_size for k in keys)
        if not messagebox.askyesno("Confirm clean",
                                   f"Permanently delete {human_size(total)} of files?\n\n"
                                   "Files that are in use will be skipped."):
            return

        def job():
            freed = failed = 0
            for key in keys:
                report = cleaner.delete_files(self.results[key].files, dry_run=False)
                cleaner.remove_empty_dirs(locations.CATEGORIES[key][1](), dry_run=False)
                freed += report.freed
                failed += report.failed
            if "trash" in keys:
                cleaner.empty_windows_recycle_bin(dry_run=False)
            self.events.put(("cleaned", (freed, failed)))

        self._run_in_background("Cleaning...", job)

    def _on_progress(self, text):
        self.status.set(text)

    def _on_scanned(self, result: scanner.ScanResult):
        self.results[result.category] = result
        self.cat_labels[result.category].config(
            text=f"{len(result.files)} files - {human_size(result.total_size)}", foreground="")
        total = sum(r.total_size for r in self.results.values())
        self.total_label["text"] = f"Reclaimable: {human_size(total)}"
        self.clean_btn["state"] = "normal"

    def _on_cleaned(self, payload):
        freed, failed = payload
        self.refresh_disk_bar()
        msg = f"Freed {human_size(freed)}."
        if failed:
            msg += f" {failed} files were in use and skipped."
        messagebox.showinfo("Done", msg)
        self.results.clear()
        for label in self.cat_labels.values():
            label.config(text="not scanned", foreground="gray")
        self.total_label["text"] = ""
        self.clean_btn["state"] = "disabled"

    # ---------- finder tab ----------
    def start_large(self):
        root = Path(self.folder.get()).expanduser()

        def job():
            files = scanner.find_large_files(root, 100 * 1024**2, limit=200)
            self.events.put(("found", [(f, "") for f in files]))

        self._run_in_background(f"Looking for large files in {root}...", job)

    def start_duplicates(self):
        root = Path(self.folder.get()).expanduser()

        def job():
            rows = []
            for group in scanner.find_duplicates(root):
                keep, *copies = group
                rows.append((keep, "keep"))
                rows += [(c, "copy") for c in copies]
            self.events.put(("found", rows))

        self._run_in_background(f"Looking for duplicates in {root} (can take a while)...", job)

    def _on_found(self, rows):
        self.tree.delete(*self.tree.get_children())
        self.extra_files = []
        for i, (entry, tag) in enumerate(rows):
            self.extra_files.append(entry)
            self.tree.insert("", "end", iid=str(i), values=(human_size(entry.size), entry.path), tags=(tag,))
            if tag == "copy":
                self.tree.selection_add(str(i))  # pre-select copies, never the original
        self.tree.tag_configure("keep", foreground="gray")
        self.status.set(f"Found {len(rows)} files.")

    def delete_selected(self):
        chosen = [self.extra_files[int(i)] for i in self.tree.selection()]
        if not chosen:
            return
        total = sum(f.size for f in chosen)
        if not messagebox.askyesno("Confirm delete",
                                   f"Permanently delete {len(chosen)} files ({human_size(total)})?"):
            return
        report = cleaner.delete_files(chosen, dry_run=False)
        for i in self.tree.selection():
            self.tree.delete(i)
        self.refresh_disk_bar()
        self.status.set(f"Deleted {report.deleted} files, freed {human_size(report.freed)}.")

    def _on_error(self, text):
        messagebox.showerror("Error", text)

    def _on_done(self, _):
        self.busy = False
        self.scan_btn["state"] = "normal"
        if self.status.get().endswith("..."):
            self.status.set("Done.")


def run():
    CleanupApp().mainloop()
