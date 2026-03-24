import subprocess

import pytest

from shipyard.edit_engine.git import (
    GitError,
    git_commit,
    git_commit_files,
    git_get_current_hash,
    git_init_if_needed,
    git_revert_last,
    is_git_repo,
)


def _configure_git(path):
    """Set git user config for a tmp repo so commits work."""
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path)


def test_git_init_creates_repo(tmp_path):
    """git_init_if_needed on a non-git dir creates .git/ and initial commit."""
    result = git_init_if_needed(tmp_path)
    assert result is True
    assert (tmp_path / ".git").is_dir()
    # Verify initial commit exists
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True
    )
    assert "shipyard: initial commit" in log.stdout


def test_git_init_idempotent(tmp_path):
    """git_init_if_needed on an existing repo returns False, no error."""
    git_init_if_needed(tmp_path)
    result = git_init_if_needed(tmp_path)
    assert result is False


def test_git_commit_single_file(tmp_path):
    """git_commit stages and commits a file, returns a commit hash."""
    git_init_if_needed(tmp_path)

    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world")

    commit_hash = git_commit("hello.txt", tmp_path, "add hello")
    assert len(commit_hash) >= 7
    # Verify commit message has prefix
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=tmp_path, capture_output=True, text=True
    )
    assert log.stdout.strip() == "shipyard: add hello"


def test_git_commit_files_multiple(tmp_path):
    """git_commit_files commits multiple files in one commit."""
    git_init_if_needed(tmp_path)

    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bbb")

    commit_hash = git_commit_files(["a.txt", "b.txt"], tmp_path, "add a and b")
    assert len(commit_hash) >= 7

    # Verify both files in the same commit
    show = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    files = show.stdout.strip().split("\n")
    assert "a.txt" in files
    assert "b.txt" in files


def test_git_revert_last_one(tmp_path):
    """git_revert_last(n=1) creates a revert commit undoing the last change."""
    git_init_if_needed(tmp_path)

    test_file = tmp_path / "data.txt"
    test_file.write_text("original")
    git_commit("data.txt", tmp_path, "add data")

    test_file.write_text("modified")
    git_commit("data.txt", tmp_path, "modify data")

    git_revert_last(tmp_path, n=1)

    # File should be back to "original"
    assert test_file.read_text() == "original"


def test_git_revert_last_multiple(tmp_path):
    """git_revert_last(n=2) reverts the last two commits."""
    git_init_if_needed(tmp_path)

    test_file = tmp_path / "data.txt"
    test_file.write_text("v1")
    git_commit("data.txt", tmp_path, "v1")

    test_file.write_text("v2")
    git_commit("data.txt", tmp_path, "v2")

    test_file.write_text("v3")
    git_commit("data.txt", tmp_path, "v3")

    git_revert_last(tmp_path, n=2)

    # Should be back to v1
    assert test_file.read_text() == "v1"


def test_git_get_current_hash(tmp_path):
    """git_get_current_hash returns a 7-char hash string."""
    git_init_if_needed(tmp_path)
    commit_hash = git_get_current_hash(tmp_path)
    assert len(commit_hash) >= 7
    # Should be hex characters
    assert all(c in "0123456789abcdef" for c in commit_hash)


def test_is_git_repo_true(tmp_path):
    """is_git_repo returns True for an initialized repo."""
    git_init_if_needed(tmp_path)
    assert is_git_repo(tmp_path) is True


def test_is_git_repo_false(tmp_path):
    """is_git_repo returns False for a plain directory."""
    assert is_git_repo(tmp_path) is False


def test_git_commit_error_on_untracked(tmp_path):
    """git_commit on a file that doesn't exist raises GitError."""
    git_init_if_needed(tmp_path)
    with pytest.raises(GitError):
        git_commit("nonexistent.txt", tmp_path, "should fail")
