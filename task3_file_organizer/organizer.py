"""File organizer: sorts the files in a folder into category subfolders.

Usage:
    python organizer.py PATH                  # organize PATH
    python organizer.py PATH --dry-run        # preview only, nothing moves
    python organizer.py PATH --recursive      # also sort files in subfolders
    python organizer.py PATH --recursive --clean-empty
                                              # ...and delete emptied folders
"""
import argparse
import logging
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CATEGORIES = {
    "Documents": (
        ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md",
        ".ppt", ".pptx", ".xls", ".xlsx", ".csv",
    ),
    "Images": (
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff",
    ),
    "Videos": (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"),
    "Archives": (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"),
    "Code": (
        ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".go",
        ".rs", ".html", ".css", ".json", ".sql", ".sh", ".ipynb",
    ),
}
# Reverse lookup: {'.pdf': 'Documents', '.jpg': 'Images', ...}
EXTENSION_MAP = {
    extension: category
    for category, extensions in CATEGORIES.items()
    for extension in extensions
}
DEFAULT_CATEGORY = "Others"
CATEGORY_NAMES = set(CATEGORIES) | {DEFAULT_CATEGORY}
LOG_FILE = "organizer.log"
SKIP_NAMES = {Path(__file__).name, LOG_FILE}

logger = logging.getLogger("organizer")


@dataclass
class Summary:
    """Result of one organizing run."""

    moved: Counter = field(default_factory=Counter)
    errors: list = field(default_factory=list)
    removed_dirs: int = 0

    @property
    def total_moved(self) -> int:
        return sum(self.moved.values())


def get_category(filename: str) -> str:
    """Pick the category folder for a file from its extension."""
    suffix = Path(filename).suffix.lower()
    return EXTENSION_MAP.get(suffix, DEFAULT_CATEGORY)


def unique_destination(destination: Path) -> Path:
    """Return a free path, adding ' (1)', ' (2)'... on a naming collision."""
    if not destination.exists():
        return destination
    counter = 1
    while True:
        name = f"{destination.stem} ({counter}){destination.suffix}"
        candidate = destination.with_name(name)
        if not candidate.exists():
            return candidate
        counter += 1


def list_files(
    folder: Path, recursive: bool = False, root: Optional[Path] = None
) -> list[Path]:
    """List regular, non-hidden files in a folder (and below if recursive).

    The category folders directly under the root are skipped, so files that
    are already organized stay where they are.
    """
    root = root or folder
    at_root = folder == root
    found: list[Path] = []
    with os.scandir(folder) as entries:
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.name.startswith("."):
                continue
            if entry.is_file(follow_symlinks=False):
                if not (at_root and entry.name in SKIP_NAMES):
                    found.append(Path(entry.path))
            elif recursive and entry.is_dir(follow_symlinks=False):
                if at_root and entry.name in CATEGORY_NAMES:
                    continue
                found.extend(list_files(Path(entry.path), True, root))
    return found


def remove_empty_dirs(root: Path) -> int:
    """Delete empty subfolders, bottom-up. Root and category folders stay."""
    removed = 0
    for current, _dirs, _files in os.walk(root, topdown=False):
        path = Path(current)
        relative = path.relative_to(root)
        if path == root or any(p.startswith(".") for p in relative.parts):
            continue
        if path.parent == root and path.name in CATEGORY_NAMES:
            continue
        try:
            path.rmdir()  # only succeeds when the folder is empty
        except OSError:
            continue
        removed += 1
        logger.info("Removed empty folder %s", relative)
    return removed


def _record_error(summary: Summary, source: Path, reason: str) -> None:
    summary.errors.append((source.name, reason))
    logger.error("Could not move %s: %s", source.name, reason)


def organize(
    folder: Path,
    dry_run: bool = False,
    recursive: bool = False,
    clean_empty: bool = False,
) -> Summary:
    """Move every file into <folder>/<Category>/ and report what happened."""
    summary = Summary()
    for source in list_files(folder, recursive):
        category = get_category(source.name)
        target_dir = folder / category
        try:
            destination = unique_destination(target_dir / source.name)
            if dry_run:
                logger.info("[dry-run] %s -> %s/", source.name, category)
            else:
                target_dir.mkdir(exist_ok=True)
                shutil.move(str(source), str(destination))
                logger.info("Moved %s -> %s/", source.name, category)
            summary.moved[category] += 1
        except PermissionError:
            _record_error(summary, source, "permission denied")
        except FileExistsError:
            _record_error(summary, source, "destination already exists")
        except OSError as exc:
            _record_error(summary, source, str(exc))
    if recursive and clean_empty and not dry_run:
        summary.removed_dirs = remove_empty_dirs(folder)
    return summary


def print_summary(summary: Summary, dry_run: bool = False) -> None:
    """Print a formatted execution summary."""
    label = "would be relocated" if dry_run else "relocated"
    print("\n===== Organization summary =====")
    for category in sorted(summary.moved):
        print(f"  {category:<12}{summary.moved[category]:>4}")
    print("--------------------------------")
    print(f"  Total files {label}: {summary.total_moved}")
    if summary.removed_dirs:
        print(f"  Empty folders removed: {summary.removed_dirs}")
    print(f"  Errors: {len(summary.errors)}")
    for name, reason in summary.errors:
        print(f"    - {name}: {reason}")


def setup_logging() -> None:
    """Log to the console and to organizer.log."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
        force=True,
    )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize a cluttered folder into category subfolders."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(Path.home() / "Downloads"),
        help="folder to organize (default: ~/Downloads)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without moving anything",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="also organize files inside subfolders",
    )
    parser.add_argument(
        "--clean-empty",
        action="store_true",
        help="with --recursive: delete subfolders left empty",
    )
    args = parser.parse_args(argv)
    if args.clean_empty and not args.recursive:
        parser.error("--clean-empty requires --recursive")
    return args


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point. Returns a process exit code."""
    args = parse_args(argv)
    folder = Path(args.path).expanduser().resolve()
    if not folder.is_dir():
        print(f"Error: '{folder}' is not a folder.", file=sys.stderr)
        return 2
    if folder == Path(folder.anchor) or folder == Path.home():
        print("Error: refusing to organize a root or home folder.",
              file=sys.stderr)
        return 2
    setup_logging()
    mode = " (dry run)" if args.dry_run else ""
    logger.info("Organizing %s%s", folder, mode)
    try:
        summary = organize(
            folder, args.dry_run, args.recursive, args.clean_empty
        )
    except OSError as exc:
        logger.error("Cannot read folder: %s", exc)
        return 1
    print_summary(summary, args.dry_run)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    sys.exit(main())
