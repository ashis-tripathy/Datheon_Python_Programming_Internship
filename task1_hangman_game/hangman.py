"""Hangman Word Guessing Game (Console) - main entry point.

Usage:
    python hangman.py
"""
import random
import sys
from typing import Callable, Optional

from ascii_art import STAGES
from game_logic import MAX_MISTAKES, get_guess, is_won, masked_word
from word_loader import load_words


def display_state(secret: str, guessed: set, wrong: set) -> None:
    """Draw the gallows, the masked word and the wrong letters so far."""
    print(STAGES[len(wrong)])
    print("\nWord:", masked_word(secret, guessed))
    print(
        "Wrong letters:",
        " ".join(sorted(letter.upper() for letter in wrong)) or "-",
    )
    print(f"Attempts left: {MAX_MISTAKES - len(wrong)}\n")


def show_victory(secret: str, mistakes: int) -> None:
    print("\n" + "=" * 40)
    print("🎉  YOU WON!  🎉".center(40))
    print(f"The word was: {secret.upper()}".center(40))
    print(f"Mistakes made: {mistakes}".center(40))
    print("=" * 40)


def show_defeat(secret: str) -> None:
    print(STAGES[-1])
    print("\n" + "=" * 40)
    print("💀  GAME OVER  💀".center(40))
    print(f"The word was: {secret.upper()}".center(40))
    print("=" * 40)


def play_game(words: list, input_fn: Callable[[str], str] = input) -> bool:
    """Play one round. Returns True if the player won."""
    if not words:
        raise ValueError("The word list is empty.")
    secret = random.choice(words)
    guessed: set = set()
    wrong: set = set()

    print("\n🎮 Welcome to HANGMAN! Guess the word in 6 mistakes or fewer.")
    while len(wrong) < MAX_MISTAKES:
        display_state(secret, guessed, wrong)
        guess = get_guess(guessed, wrong, input_fn)

        if guess in secret:
            guessed.add(guess)
            print(f"✅ Good guess! '{guess.upper()}' is in the word.")
            if is_won(secret, guessed):
                print(STAGES[len(wrong)])
                print("\nWord:", masked_word(secret, guessed))
                show_victory(secret, len(wrong))
                return True
        else:
            wrong.add(guess)
            print(f"❌ '{guess.upper()}' is not in the word.")

    show_defeat(secret)
    return False


def main(
    words: Optional[list] = None,
    input_fn: Callable[[str], str] = input,
) -> int:
    """Entry point. Returns a process exit code."""
    words = words or load_words()
    try:
        while True:
            play_game(words, input_fn)
            again = input_fn("\nPlay again? (y/n): ").strip().lower()
            if again != "y":
                print("Thanks for playing! 👋")
                break
    except (KeyboardInterrupt, EOFError):
        print("\nGame ended. Bye! 👋")
    return 0


def configure_output() -> None:
    """Use UTF-8 output so the emoji never crash a legacy console."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    configure_output()
    sys.exit(main())
