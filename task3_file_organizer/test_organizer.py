from pathlib import Path

import pytest

import organizer


def make_files(folder, *names):
    for name in names:
        (folder / name).write_text(name)


@pytest.mark.parametrize("name,expected", [
    ("report.PDF", "Documents"),
    ("photo.jpg", "Images"),
    ("clip.mp4", "Videos"),
    ("backup.zip", "Archives"),
    ("script.py", "Code"),
    ("mystery.xyz", "Others"),
    ("no_extension", "Others"),
])
def test_get_category(name, expected):
    assert organizer.get_category(name) == expected


def test_files_move_into_category_folders(tmp_path):
    make_files(tmp_path, "a.pdf", "b.jpg", "c.zip", "d.py", "e.xyz")
    summary = organizer.organize(tmp_path)
    assert summary.total_moved == 5 and not summary.errors
    assert (tmp_path / "Documents" / "a.pdf").exists()
    assert (tmp_path / "Images" / "b.jpg").exists()
    assert (tmp_path / "Archives" / "c.zip").exists()
    assert (tmp_path / "Code" / "d.py").exists()
    assert (tmp_path / "Others" / "e.xyz").exists()
    assert not (tmp_path / "a.pdf").exists()


def test_naming_collision_gets_a_unique_name(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "a.pdf").write_text("old")
    (tmp_path / "a.pdf").write_text("new")
    organizer.organize(tmp_path)
    assert (tmp_path / "Documents" / "a.pdf").read_text() == "old"
    assert (tmp_path / "Documents" / "a (1).pdf").read_text() == "new"


def test_unique_destination_skips_taken_names(tmp_path):
    make_files(tmp_path, "x.txt", "x (1).txt")
    assert organizer.unique_destination(tmp_path / "x.txt").name == (
        "x (2).txt"
    )


def test_dry_run_moves_nothing(tmp_path):
    make_files(tmp_path, "a.pdf", "b.jpg")
    summary = organizer.organize(tmp_path, dry_run=True)
    assert summary.total_moved == 2
    assert (tmp_path / "a.pdf").exists()
    assert not (tmp_path / "Documents").exists()


def test_permission_error_is_recorded_not_raised(tmp_path, monkeypatch):
    make_files(tmp_path, "a.pdf")

    def denied(src, dst):
        raise PermissionError("denied")

    monkeypatch.setattr(organizer.shutil, "move", denied)
    summary = organizer.organize(tmp_path)
    assert summary.total_moved == 0
    assert summary.errors == [("a.pdf", "permission denied")]


def test_file_exists_error_is_recorded(tmp_path, monkeypatch):
    make_files(tmp_path, "a.pdf")

    def exists(src, dst):
        raise FileExistsError("exists")

    monkeypatch.setattr(organizer.shutil, "move", exists)
    summary = organizer.organize(tmp_path)
    assert summary.errors == [("a.pdf", "destination already exists")]


def test_hidden_files_and_folders_are_ignored(tmp_path):
    make_files(tmp_path, ".hidden.txt")
    (tmp_path / "subfolder").mkdir()
    summary = organizer.organize(tmp_path)
    assert summary.total_moved == 0
    assert (tmp_path / ".hidden.txt").exists()


def test_main_rejects_missing_folder(tmp_path):
    assert organizer.main([str(tmp_path / "nope")]) == 2


def test_main_refuses_home_folder():
    assert organizer.main([str(Path.home())]) == 2


def test_main_organizes_folder(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # keeps organizer.log out of the project
    folder = tmp_path / "downloads"
    folder.mkdir()
    make_files(folder, "a.pdf", "b.png")
    assert organizer.main([str(folder)]) == 0
    assert "Total files relocated: 2" in capsys.readouterr().out
    assert (folder / "Images" / "b.png").exists()


# ------------------------------------------------------ recursive mode
def test_recursive_moves_nested_files(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    make_files(tmp_path, "top.zip")
    make_files(tmp_path / "a", "x.pdf")
    make_files(tmp_path / "a" / "b", "y.jpg")
    summary = organizer.organize(tmp_path, recursive=True)
    assert summary.total_moved == 3 and not summary.errors
    assert (tmp_path / "Archives" / "top.zip").exists()
    assert (tmp_path / "Documents" / "x.pdf").exists()
    assert (tmp_path / "Images" / "y.jpg").exists()
    assert (tmp_path / "a" / "b").exists()  # folders stay unless cleaned


def test_default_mode_ignores_nested_files(tmp_path):
    (tmp_path / "a").mkdir()
    make_files(tmp_path / "a", "x.pdf")
    assert organizer.organize(tmp_path).total_moved == 0
    assert (tmp_path / "a" / "x.pdf").exists()


def test_recursive_leaves_organized_category_folders_alone(tmp_path):
    (tmp_path / "Documents").mkdir()
    make_files(tmp_path / "Documents", "old.pdf")
    summary = organizer.organize(tmp_path, recursive=True)
    assert summary.total_moved == 0
    assert (tmp_path / "Documents" / "old.pdf").exists()


def test_recursive_ignores_hidden_folders(tmp_path):
    (tmp_path / ".git").mkdir()
    make_files(tmp_path / ".git", "config.txt")
    assert organizer.organize(tmp_path, recursive=True).total_moved == 0
    assert (tmp_path / ".git" / "config.txt").exists()


def test_clean_empty_removes_only_empty_folders(tmp_path):
    (tmp_path / "junk" / "deep").mkdir(parents=True)
    make_files(tmp_path / "junk" / "deep", "a.pdf")
    (tmp_path / "keep").mkdir()
    make_files(tmp_path / "keep", ".hidden")  # hidden file: not moved
    summary = organizer.organize(tmp_path, recursive=True, clean_empty=True)
    assert summary.removed_dirs == 2
    assert not (tmp_path / "junk").exists()
    assert (tmp_path / "keep").exists()
    assert (tmp_path / "Documents" / "a.pdf").exists()


def test_clean_empty_does_nothing_on_dry_run(tmp_path):
    (tmp_path / "junk").mkdir()
    make_files(tmp_path / "junk", "a.pdf")
    summary = organizer.organize(
        tmp_path, dry_run=True, recursive=True, clean_empty=True
    )
    assert summary.removed_dirs == 0
    assert (tmp_path / "junk" / "a.pdf").exists()


def test_clean_empty_requires_recursive(tmp_path):
    with pytest.raises(SystemExit):
        organizer.main([str(tmp_path), "--clean-empty"])
