import pytest

import ascii_art
import game_logic
import hangman
import word_loader


def scripted(*answers):
    replies = iter(answers)
    return lambda _prompt="": next(replies)


# ------------------------------------------------------- game_logic
def test_masked_word_hides_unguessed_letters():
    assert game_logic.masked_word("python", {"p", "o"}) == "P _ _ _ O _"


def test_masked_word_reveals_everything_when_all_guessed():
    assert game_logic.masked_word("hi", {"h", "i"}) == "H I"


def test_is_won_true_when_all_letters_guessed():
    assert game_logic.is_won("cat", {"c", "a", "t", "z"}) is True


def test_is_won_false_when_letters_missing():
    assert game_logic.is_won("cat", {"c", "a"}) is False


def test_is_valid_letter():
    assert game_logic.is_valid_letter("a") and game_logic.is_valid_letter("Z")
    for bad in ["", "ab", "1", "!", " ", "é"]:
        assert not game_logic.is_valid_letter(bad)


def test_get_guess_rejects_invalid_input():
    answer = game_logic.get_guess(
        set(), set(), scripted("", "ab", "1", "!", "A")
    )
    assert answer == "a"


def test_get_guess_rejects_non_ascii_letters():
    assert game_logic.get_guess(set(), set(), scripted("é", "e")) == "e"


def test_get_guess_rejects_duplicates(capsys):
    answer = game_logic.get_guess({"a"}, {"z"}, scripted("a", "z", "b"))
    assert answer == "b"
    assert "already guessed" in capsys.readouterr().out


def test_get_guess_lowercases_and_strips():
    assert game_logic.get_guess(set(), set(), scripted("  Q ")) == "q"


# ------------------------------------------------------ word_loader
def test_load_words_filters_by_length_and_letters(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("cat\nPython\nhello1\nverylongwordhere\nhangman\n")
    assert word_loader.load_words(path) == ["python", "hangman"]


def test_load_words_missing_file_uses_fallback(tmp_path):
    result = word_loader.load_words(tmp_path / "none.txt")
    assert result == word_loader.FALLBACK_WORDS


def test_load_words_folder_path_uses_fallback(tmp_path):
    assert word_loader.load_words(tmp_path) == word_loader.FALLBACK_WORDS


def test_load_words_undecodable_file_uses_fallback(tmp_path):
    path = tmp_path / "words.txt"
    path.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    assert word_loader.load_words(path) == word_loader.FALLBACK_WORDS


def test_load_words_with_no_usable_word_uses_fallback(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("a\nbb\n123\n")
    assert word_loader.load_words(path) == word_loader.FALLBACK_WORDS


def test_load_words_handles_bom_and_windows_line_endings(tmp_path):
    path = tmp_path / "words.txt"
    path.write_bytes(b"\xef\xbb\xbfplanet\r\ngarden\r\n")
    assert word_loader.load_words(path) == ["planet", "garden"]


# ------------------------------------------------------- game rounds
def test_every_mistake_count_has_gallows_art():
    assert len(ascii_art.STAGES) == game_logic.MAX_MISTAKES + 1


def test_display_state_shows_wrong_letters_and_attempts(capsys):
    hangman.display_state("python", {"p"}, {"z", "a"})
    out = capsys.readouterr().out
    assert "P _ _ _ _ _" in out
    assert "Wrong letters: A Z" in out
    assert "Attempts left: 4" in out


def test_play_game_win(capsys):
    won = hangman.play_game(["python"], scripted(*"python"))
    assert won is True
    out = capsys.readouterr().out
    assert "YOU WON" in out and "Mistakes made: 0" in out


def test_play_game_loss_after_six_mistakes(capsys):
    won = hangman.play_game(["python"], scripted(*"zxqwvk"))
    assert won is False
    out = capsys.readouterr().out
    assert "GAME OVER" in out and "PYTHON" in out


def test_duplicate_wrong_guess_costs_nothing(capsys):
    won = hangman.play_game(["python"], scripted("z", "z", *"python"))
    assert won is True
    out = capsys.readouterr().out
    assert "already guessed" in out
    assert "Mistakes made: 1" in out


def test_play_game_rejects_an_empty_word_list():
    with pytest.raises(ValueError):
        hangman.play_game([], scripted("a"))


def test_main_plays_one_round_then_quits(capsys):
    code = hangman.main(["python"], scripted(*"python", "n"))
    assert code == 0
    assert "Thanks for playing" in capsys.readouterr().out


def test_main_survives_end_of_input(capsys):
    def no_input(_prompt=""):
        raise EOFError

    assert hangman.main(["python"], no_input) == 0
    assert "Bye" in capsys.readouterr().out
