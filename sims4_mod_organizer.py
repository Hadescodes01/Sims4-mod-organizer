#!/usr/bin/env python3
"""
Sims 4 Mod Organizer
=====================
A simple desktop app (Tkinter) that automatically sorts your Sims 4
Mods folder into tidy subfolders:

    Clothes / Hair / Skin_Makeup / Build_Buy / Gameplay / Food /
    Poses_Animations / Unsorted

How it works
------------
Every .package and .ts4script file in your Mods folder (and its
subfolders) is inspected. The filename is compared against curated
keyword lists to guess which category it belongs to. You get a
preview table before anything is touched, and you can right-click any
row to change its category if the guess is wrong. Files that can't be
confidently guessed land in "Unsorted" so you can glance through them
instead of hunting through thousands of files one by one.

Read-me files (readme.txt, Read Me.md, etc.) found alongside your mods
can optionally be collected into a ReadMe folder, sorted into
subfolders named after the mod they came from, so nothing gets lost
even after the originals move.

Files are MOVED or COPIED (your choice) into new subfolders inside
your Mods folder; nothing is ever deleted unless you explicitly tick
"Delete empty folders left behind after organizing," which only
removes folders that are already empty once everything's been sorted
— the whole point being to keep your Mods folder as short as
possible. Every organize run is logged so you can Undo it with one
click.

Run it with:  python3 sims4_mod_organizer.py
(Requires Python 3 with Tkinter/Tk support.)
"""

import os
import re
import json
import shutil
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Sims 4 Mod Organizer"
UNDO_FILE_NAME = ".sims4_mod_organizer_undo.json"
VALID_EXTENSIONS = (".package", ".ts4script")
THUMBNAIL_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
README_FOLDER_NAME = "ReadMe"
README_EXTENSIONS = (".txt", ".md", ".rtf", ".pdf", ".doc", ".docx", ".html", ".htm")
README_NAME_PATTERN = re.compile(r"read[\s_\-]?me", re.IGNORECASE)

CATEGORIES = [
    "Clothes",
    "Hair",
    "Skin_Makeup",
    "Build_Buy",
    "Gameplay",
    "Food",
    "Poses_Animations",
    "Unsorted",
]

# Order matters: more specific / less ambiguous categories are checked first
# so a file isn't mis-caught by a generic keyword in a later category.
PRIORITY_ORDER = [
    "Poses_Animations",
    "Hair",
    "Skin_Makeup",
    "Food",
    "Build_Buy",
    "Clothes",
    "Gameplay",
]

KEYWORDS = {
    "Hair": [
        "hair", "wig", "braid", "braids", "ponytail", "pigtail", "bun",
        "updo", "afro", "dreadlock", "dreadlocks", "bangs", "fringe",
        "curls", "curly", "cornrow", "cornrows", "buzzcut", "mohawk",
        "toddlerhair", "childhair", "hairstyle",
    ],
    "Clothes": [
        "shirt", "tshirt", "dress", "pants", "shoe", "shoes", "boot",
        "boots", "sneaker", "sneakers", "heel", "heels", "jacket",
        "coat", "swim", "swimsuit", "bikini", "outfit", "top", "bottom",
        "jean", "jeans", "skirt", "hoodie", "sweater", "cardigan",
        "romper", "jumpsuit", "lingerie", "bra", "underwear", "earring",
        "earrings", "necklace", "bracelet", "ring", "glasses",
        "sunglasses", "hat", "cap", "beanie", "piercing",
        "socks", "gloves", "tie", "scarf",
        "shorts", "leggings", "vest", "blazer", "cas",
    ],
    "Skin_Makeup": [
        "makeup", "lipstick", "lipgloss", "lip", "eyeliner", "eyeshadow",
        "blush", "highlighter", "contour", "foundation", "nails",
        "nailpolish", "skinoverlay", "skindetail", "skindetails",
        "skinblend", "skin", "freckle", "freckles", "mole", "moles",
        "tattoo", "tattoos", "eyebrow", "eyebrows", "eyelash",
        "eyelashes", "lashes", "scar", "scars", "birthmark", "overlay",
    ],
    "Build_Buy": [
        "wall", "walls", "floor", "floors", "wallpaper", "flooring",
        "furniture", "chair", "table", "sofa", "couch", "bed", "decor",
        "rug", "curtain", "curtains", "shelf", "shelves", "lighting",
        "lamp", "kitchen", "bathroom", "door", "window", "stair",
        "stairs", "fence", "pool", "roof", "counter", "cabinet",
        "bookcase", "plant", "painting", "mirror", "clutter", "buildbuy",
        "build", "houseplan", "lot", "terrain", "roomset", "ceiling",
        "fireplace", "rug", "vase", "shower", "bathtub", "sink",
    ],
    "Gameplay": [
        "mod", "tuning", "trait", "traits", "career", "careers", "skill",
        "skills", "mccc", "overhaul", "script", "gameplay", "interaction",
        "interactions", "aspiration", "aspirations", "reward", "cheat",
        "fix", "tweak", "relationship", "pregnancy", "weather",
        "university", "seasons", "expansion", "rules", "settings",
        "storyprogression", "autonomy",
    ],
    "Food": [
        "food", "recipe", "recipes", "meal", "drink", "cake", "cook",
        "cooking", "restaurant", "menu", "snack", "dessert", "fruit",
        "vegetable", "cuisine", "beverage", "coffee", "cocktail",
        "pizza", "burger", "bakery", "candy", "icecream",
    ],
    "Poses_Animations": [
        "pose", "poses", "posepack", "posebox", "anim", "animation",
        "animations", "posesbytechyx", "cas pose", "couple pose",
        "action pose", "posestand",
    ],
}


def normalize(text):
    """Lowercase and replace common separators with spaces so word-boundary
    matching works on tokens like 'hair_clip' or 'CAS-Hair.package'."""
    return re.sub(r"[_\-.]", " ", text.lower())


def is_readme(filename):
    """True if filename looks like a read-me file we should collect
    (matches 'readme'/'read me'/'read_me' with a common doc extension)."""
    base, ext = os.path.splitext(filename)
    if ext.lower() not in README_EXTENSIONS:
        return False
    return bool(README_NAME_PATTERN.search(base))


def sanitize_foldername(name):
    """Strip characters that aren't safe in a folder name on Windows/macOS."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip()
    return cleaned or "General"


def categorize(filename):
    """Guess a category for a single filename. Returns one of CATEGORIES."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".ts4script":
        return "Gameplay"

    text = normalize(filename)
    for cat in PRIORITY_ORDER:
        for kw in KEYWORDS[cat]:
            if " " in kw:
                if kw in text:
                    return cat
            else:
                if re.search(r"\b" + re.escape(kw) + r"\b", text):
                    return cat
    return "Unsorted"


def find_default_mods_folder():
    """Try a couple of common Sims 4 Mods folder locations."""
    candidates = [
        os.path.expanduser("~/Documents/Electronic Arts/The Sims 4/Mods"),
        os.path.expanduser("~/OneDrive/Documents/Electronic Arts/The Sims 4/Mods"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def scan_folder(root_folder):
    """Walk root_folder and return (mod_items, readme_items).

    mod_items: list of dicts describing each mod file found, with a guessed
    category. Skips descending into folders that are already one of our
    category subfolders directly under root.

    readme_items: list of dicts describing read-me files found alongside
    mods, with the name of the mod folder they came from so they can be
    collected into a ReadMe folder without losing track of which mod they
    belong to.
    """
    root_folder = os.path.abspath(root_folder)
    category_dirs_abs = {os.path.join(root_folder, c) for c in CATEGORIES}
    readme_dir_abs = os.path.join(root_folder, README_FOLDER_NAME)

    items = []
    readmes = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        dirpath_abs = os.path.abspath(dirpath)
        if dirpath_abs in category_dirs_abs or dirpath_abs == readme_dir_abs:
            dirnames[:] = []  # don't recurse into already-organized folders
            continue

        # Companion thumbnails (e.g. CoolHair.jpg next to CoolHair.package)
        # are matched by base filename within this same folder, so they can
        # travel with their mod later instead of getting their own folder.
        thumb_lookup = {}
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in THUMBNAIL_EXTENSIONS:
                base = os.path.splitext(fname)[0]
                thumb_lookup.setdefault(base, []).append(fname)

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, root_folder)

            if ext in VALID_EXTENSIONS:
                base = os.path.splitext(fname)[0]
                thumbnails = [
                    {"path": os.path.join(dirpath, t), "name": t}
                    for t in thumb_lookup.get(base, [])
                ]
                items.append({
                    "path": full_path,
                    "name": fname,
                    "relpath": rel_path,
                    "category": categorize(fname),
                    "thumbnails": thumbnails,
                })
            elif is_readme(fname):
                mod_name = (
                    os.path.basename(dirpath_abs)
                    if dirpath_abs != root_folder
                    else "General"
                )
                readmes.append({
                    "path": full_path,
                    "name": fname,
                    "relpath": rel_path,
                    "mod_name": mod_name,
                })
    return items, readmes


def unique_destination(dest_dir, filename):
    """Return a path inside dest_dir for filename, adding ' (2)', ' (3)', ...
    if a file with that name already exists there."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(dest_dir, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


def delete_empty_folders(root_folder, keep_dirs):
    """Remove now-empty subfolders left behind after organizing, so the
    Mods folder stays as short/flat as possible. Never touches root_folder
    itself or any path in keep_dirs (e.g. the category / ReadMe folders).
    Walks bottom-up so nested empty folders cascade-delete correctly."""
    root_folder_abs = os.path.abspath(root_folder)
    keep_dirs_abs = {os.path.abspath(d) for d in keep_dirs}
    removed = []

    for dirpath, dirnames, filenames in os.walk(root_folder_abs, topdown=False):
        dirpath_abs = os.path.abspath(dirpath)
        if dirpath_abs == root_folder_abs or dirpath_abs in keep_dirs_abs:
            continue
        try:
            if not os.listdir(dirpath_abs):
                os.rmdir(dirpath_abs)
                removed.append(dirpath_abs)
        except OSError:
            pass  # not empty (race) or permission issue — just skip it

    return removed


class Sims4OrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x640")
        self.minsize(820, 520)

        self.mods_root = None
        self.scanned_items = []  # list of dicts, index == treeview iid
        self.readme_items = []  # read-me files found alongside mods
        self.copy_mode = tk.BooleanVar(value=False)
        self.collect_readmes = tk.BooleanVar(value=True)
        self.delete_empty = tk.BooleanVar(value=False)
        self.filter_category = tk.StringVar(value="All")
        self.search_text = tk.StringVar(value="")

        self._apply_capybara_theme()
        self._build_widgets()

    # ---------------------------------------------------------------- UI

    def _apply_capybara_theme(self):
        """A warm, capybara-burrow palette matching the portfolio site:
        tan backgrounds, brown accents, sage highlights."""
        bg = "#F3E7D6"
        panel = "#FBF4E8"
        panel_alt = "#EDDCBC"
        border = "#DDC6A1"
        text = "#4A3524"
        text_muted = "#8A6F53"
        accent = "#A9714A"
        accent_hover = "#8A5C3A"
        sage = "#83957A"
        white = "#FFFDF8"

        self.configure(bg=bg)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass  # fall back to whatever default theme is available

        style.configure(".", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Header.TLabel", background=bg, foreground=accent,
                         font=("Segoe UI", 15, "bold"))
        style.configure("Sub.TLabel", background=bg, foreground=text_muted,
                         font=("Segoe UI", 9))
        style.configure("TLabelframe", background=bg, foreground=text, bordercolor=border)
        style.configure("TLabelframe.Label", background=bg, foreground=accent,
                         font=("Segoe UI", 9, "bold"))

        style.configure("TButton", background=accent, foreground=white,
                         padding=7, font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("TButton", background=[("active", accent_hover)])

        style.configure("TCheckbutton", background=bg, foreground=text)
        style.map("TCheckbutton", background=[("active", bg)])

        style.configure("TCombobox", fieldbackground=white, background=white, foreground=text)
        style.configure("TEntry", fieldbackground=white, foreground=text)

        style.configure("Treeview", background=white, fieldbackground=white,
                         foreground=text, rowheight=24, bordercolor=border)
        style.configure("Treeview.Heading", background=panel_alt, foreground=text,
                         font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", accent)], foreground=[("selected", white)])
        style.map("Treeview.Heading", background=[("active", panel_alt)])

        style.configure("TScrollbar", background=panel_alt, troughcolor=bg, bordercolor=border)

        self._palette = {
            "bg": bg, "panel": panel, "panel_alt": panel_alt, "border": border,
            "text": text, "text_muted": text_muted, "accent": accent, "sage": sage, "white": white,
        }

    def _build_widgets(self):
        banner = ttk.Frame(self, padding=(14, 12, 14, 0))
        banner.pack(fill="x")
        ttk.Label(banner, text="🐹  Sims 4 Mod Organizer", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            banner,
            text="Keep your Mods folder short & sweet — organize, then tidy up the leftovers.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Mods folder:").pack(side="left")
        self.folder_label = ttk.Label(top, text="(none selected)", foreground="#8A6F53")
        self.folder_label.pack(side="left", padx=(6, 12))

        ttk.Button(top, text="Choose Folder...", command=self.choose_folder).pack(side="left")
        ttk.Button(top, text="Auto-Detect", command=self.auto_detect_folder).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Scan", command=self.scan).pack(side="left", padx=(12, 0))

        filt = ttk.Frame(self, padding=(10, 0))
        filt.pack(fill="x")
        ttk.Label(filt, text="Filter:").pack(side="left")
        cat_choices = ["All"] + CATEGORIES
        self.filter_combo = ttk.Combobox(filt, values=cat_choices, textvariable=self.filter_category,
                                          state="readonly", width=16)
        self.filter_combo.pack(side="left", padx=(6, 12))
        self.filter_combo.bind("<<ComboboxSelected>>", lambda e: self.populate_tree())

        ttk.Label(filt, text="Search:").pack(side="left")
        search_entry = ttk.Entry(filt, textvariable=self.search_text, width=30)
        search_entry.pack(side="left", padx=(6, 0))
        search_entry.bind("<KeyRelease>", lambda e: self.populate_tree())

        self.counts_label = ttk.Label(filt, text="")
        self.counts_label.pack(side="right")

        # Treeview
        tree_frame = ttk.Frame(self, padding=10)
        tree_frame.pack(fill="both", expand=True)

        columns = ("filename", "relpath", "category")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("filename", text="Filename")
        self.tree.heading("relpath", text="Current Location (relative)")
        self.tree.heading("category", text="Category (right-click to change)")
        self.tree.column("filename", width=300)
        self.tree.column("relpath", width=380)
        self.tree.column("category", width=180)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Button-2>", self._show_context_menu)  # some Mac setups

        self.context_menu = tk.Menu(self, tearoff=0)
        for cat in CATEGORIES:
            self.context_menu.add_command(label=f"Move to: {cat}",
                                           command=lambda c=cat: self._reassign_selected(c))

        # Bottom controls
        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="x")

        options_row = ttk.Frame(bottom)
        options_row.pack(fill="x")
        ttk.Checkbutton(options_row, text="Copy instead of move (keeps originals in place)",
                         variable=self.copy_mode).pack(side="left")
        ttk.Checkbutton(options_row, text="Collect read-me files into a ReadMe folder",
                         variable=self.collect_readmes).pack(side="left", padx=(18, 0))

        options_row2 = ttk.Frame(bottom)
        options_row2.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(options_row2, text="Delete empty folders left behind after organizing",
                         variable=self.delete_empty).pack(side="left")

        button_row = ttk.Frame(bottom)
        button_row.pack(fill="x", pady=(10, 0))
        ttk.Button(button_row, text="Organize Now", command=self.organize).pack(side="right")
        ttk.Button(button_row, text="Undo Last Organize", command=self.undo_last).pack(side="right", padx=(0, 8))

        # Log
        log_frame = ttk.LabelFrame(self, text="Log", padding=6)
        log_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, height=6, state="disabled", wrap="word")
        self.log_text.pack(fill="x")

    # ------------------------------------------------------------- logic

    def log(self, message):
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Select your Sims 4 Mods folder")
        if folder:
            self.mods_root = folder
            self.folder_label.configure(text=folder)
            self.log(f"Selected folder: {folder}")

    def auto_detect_folder(self):
        found = find_default_mods_folder()
        if found:
            self.mods_root = found
            self.folder_label.configure(text=found)
            self.log(f"Auto-detected Mods folder: {found}")
        else:
            messagebox.showinfo(APP_TITLE,
                                 "Couldn't auto-detect your Mods folder. Please choose it manually.\n\n"
                                 "It's usually at:\nDocuments/Electronic Arts/The Sims 4/Mods")

    def scan(self):
        if not self.mods_root or not os.path.isdir(self.mods_root):
            messagebox.showwarning(APP_TITLE, "Please choose a valid Mods folder first.")
            return
        try:
            self.scanned_items, self.readme_items = scan_folder(self.mods_root)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Scan failed:\n{e}")
            self.log(f"Scan failed: {e}\n{traceback.format_exc()}")
            return

        self.log(
            f"Scan complete: found {len(self.scanned_items)} mod file(s) "
            f"and {len(self.readme_items)} read-me file(s)."
        )
        self.populate_tree()

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        cat_filter = self.filter_category.get()
        search = self.search_text.get().lower().strip()

        for idx, item in enumerate(self.scanned_items):
            if cat_filter != "All" and item["category"] != cat_filter:
                continue
            if search and search not in item["name"].lower():
                continue
            self.tree.insert("", "end", iid=str(idx),
                              values=(item["name"], item["relpath"], item["category"]))
        self._refresh_counts()

    def _refresh_counts(self):
        counts = {c: 0 for c in CATEGORIES}
        for item in self.scanned_items:
            counts[item["category"]] = counts.get(item["category"], 0) + 1
        summary = "  |  ".join(f"{c}: {counts[c]}" for c in CATEGORIES)
        self.counts_label.configure(text=summary)

    def _show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            if row_id not in self.tree.selection():
                self.tree.selection_set(row_id)
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def _reassign_selected(self, new_category):
        selected = self.tree.selection()
        for iid in selected:
            idx = int(iid)
            self.scanned_items[idx]["category"] = new_category
            self.tree.set(iid, "category", new_category)
        self._refresh_counts()
        self.log(f"Reassigned {len(selected)} file(s) to '{new_category}'.")

    def organize(self):
        if not self.scanned_items and not self.readme_items:
            messagebox.showinfo(APP_TITLE, "Nothing to organize yet. Click Scan first.")
            return

        collect_readmes = self.collect_readmes.get() and bool(self.readme_items)
        mode = "copy" if self.copy_mode.get() else "move"

        thumb_total = sum(len(item.get("thumbnails", [])) for item in self.scanned_items)

        total_count = len(self.scanned_items) + (len(self.readme_items) if collect_readmes else 0)
        confirm_msg = (
            f"About to {mode.upper()} {len(self.scanned_items)} mod file(s) into category "
            f"subfolders inside:\n\n{self.mods_root}"
        )
        if thumb_total:
            confirm_msg += f"\n\n...bringing {thumb_total} matching thumbnail(s) along with their mods."
        if collect_readmes:
            confirm_msg += f"\n\n...and collect {len(self.readme_items)} read-me file(s) into a '{README_FOLDER_NAME}' folder."
        if not self.copy_mode.get() and self.delete_empty.get():
            confirm_msg += "\n\n...and delete any folders left empty afterward."
        confirm_msg += "\n\nContinue?"

        if total_count and not messagebox.askyesno(APP_TITLE, confirm_msg):
            return

        # Build one combined action list so mods, their thumbnails, and
        # read-mes all share the same move/copy + undo-manifest logic.
        # Thumbnails go into the exact same destination folder as their mod
        # (same filename base) so managers/the game still recognize them —
        # they never get a folder of their own.
        actions = []
        thumb_count = 0
        for item in self.scanned_items:
            dest_dir = os.path.join(self.mods_root, item["category"])
            actions.append((item["path"], dest_dir, item["name"]))
            for thumb in item.get("thumbnails", []):
                actions.append((thumb["path"], dest_dir, thumb["name"]))
                thumb_count += 1
        if collect_readmes:
            readme_root = os.path.join(self.mods_root, README_FOLDER_NAME)
            actions += [
                (r["path"], os.path.join(readme_root, sanitize_foldername(r["mod_name"])), r["name"])
                for r in self.readme_items
            ]

        manifest = []
        errors = []
        for src, dest_dir, name in actions:
            if not os.path.exists(src):
                continue  # already moved in a prior run, or missing
            os.makedirs(dest_dir, exist_ok=True)
            dest = unique_destination(dest_dir, name)
            try:
                if self.copy_mode.get():
                    shutil.copy2(src, dest)
                else:
                    shutil.move(src, dest)
                manifest.append({"from": src, "to": dest, "copied": self.copy_mode.get()})
            except Exception as e:
                errors.append(f"{name}: {e}")

        manifest_path = os.path.join(self.mods_root, UNDO_FILE_NAME)
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            self.log(f"Warning: couldn't write undo log: {e}")

        self.log(f"Organized {len(manifest)} file(s) ({mode}), including {thumb_count} thumbnail(s). {len(errors)} error(s).")
        for err in errors:
            self.log(f"  ERROR: {err}")

        removed_folders = []
        if not self.copy_mode.get() and self.delete_empty.get():
            keep_dirs = [os.path.join(self.mods_root, c) for c in CATEGORIES]
            keep_dirs.append(os.path.join(self.mods_root, README_FOLDER_NAME))
            removed_folders = delete_empty_folders(self.mods_root, keep_dirs)
            if removed_folders:
                self.log(f"Removed {len(removed_folders)} empty folder(s).")

        msg = f"Done! {len(manifest)} file(s) organized."
        if removed_folders:
            msg += f"\n{len(removed_folders)} empty folder(s) removed."
        if errors:
            msg += f"\n{len(errors)} file(s) failed — see the log for details."
        messagebox.showinfo(APP_TITLE, msg)

        # Rescan so the view reflects the new locations
        self.scan()

    def undo_last(self):
        if not self.mods_root:
            messagebox.showwarning(APP_TITLE, "Please choose your Mods folder first.")
            return
        manifest_path = os.path.join(self.mods_root, UNDO_FILE_NAME)
        if not os.path.exists(manifest_path):
            messagebox.showinfo(APP_TITLE, "No previous organize run found to undo.")
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Couldn't read undo log:\n{e}")
            return

        if not messagebox.askyesno(APP_TITLE, f"Undo the last organize run ({len(manifest)} file(s))?"):
            return

        undone = 0
        errors = []
        for entry in manifest:
            src, dst, copied = entry["from"], entry["to"], entry.get("copied", False)
            try:
                if copied:
                    if os.path.exists(dst):
                        os.remove(dst)
                else:
                    if os.path.exists(dst):
                        os.makedirs(os.path.dirname(src), exist_ok=True)
                        shutil.move(dst, src)
                undone += 1
            except Exception as e:
                errors.append(f"{os.path.basename(dst)}: {e}")

        try:
            os.remove(manifest_path)
        except Exception:
            pass

        self.log(f"Undo complete: {undone} file(s) restored. {len(errors)} error(s).")
        for err in errors:
            self.log(f"  ERROR: {err}")
        messagebox.showinfo(APP_TITLE, f"Undo complete: {undone} file(s) restored.")
        self.scan()


def main():
    app = Sims4OrganizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
