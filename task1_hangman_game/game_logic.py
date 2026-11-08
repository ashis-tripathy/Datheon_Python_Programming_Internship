"""Core game helpers: masking, input validation, win check."""
from typing import Callable

MAX_MISTAKES = 6


def masked_word(secret: str, guessed: set) -> str:
    """Show guessed letters and underscores, e.g. '_ Y T H _ N'."""
    return " ".join(ch.upper() if ch in guessed else "_" for ch in secret)


def is_won(secret: str, guessed: set) -> bool:
    """True when every letter of the secret word has been guessed."""
    return all(ch in guessed for ch in secret)


def is_valid_letter(text: str) -> bool:
    """True for exactly one ASCII letter (a-z or A-Z)."""
    return len(text) == 1 and text.isascii() and text.isalpha()


def get_guess(
    guessed: set, wrong: set, input_fn: Callable[[str], str] = input
) -> str:
    """Ask until the player gives a new single letter. Repeats cost nothing."""
    while True:
        guess = input_fn("Guess a letter: ").strip().lower()
        if not is_valid_letter(guess):
            print("⚠️  Enter a single letter (A-Z).")
        elif guess in guessed or guess in wrong:
            print(
                f"⚠️  You already guessed '{guess.upper()}'. "
                "No penalty, try another."
            )
        else:
            return guess
