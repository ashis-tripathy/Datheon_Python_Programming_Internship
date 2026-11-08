"""Loads and filters the English word list (words.txt)."""
from pathlib import Path
from typing import Optional

DEFAULT_PATH = Path(__file__).resolve().parent / "words.txt"
FALLBACK_WORDS = [
    "python", "hangman", "program", "keyboard", "network", "variable",
]


def load_words(
    path: Optional[Path] = None, min_len: int = 5, max_len: int = 10
) -> list[str]:
    """Return lowercase alphabetic words of min_len..max_len letters.

    Falls back to a small built-in list if the file is missing, unreadable
    or has no usable words.
    """
    path = Path(path) if path else DEFAULT_PATH
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        print(f"{path.name} not found, using built-in words.")
        return list(FALLBACK_WORDS)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Could not read {path.name} ({exc}), using built-in words.")
        return list(FALLBACK_WORDS)
    words = [line.strip().lower() for line in lines]
    words = [
        w for w in words
        if w.isascii() and w.isalpha() and min_len <= len(w) <= max_len
    ]
    return words or list(FALLBACK_WORDS)
