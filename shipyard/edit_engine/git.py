import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""
    pass


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """
    Internal helper to run a git command.

    Raises GitError with stderr content on non-zero exit code.
    All git commands should go through this helper.
    """
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip())
    return result


def git_init_if_needed(project_root: Path) -> bool:
    """
    Ensure the project directory is a git repo.
    If .git/ doesn't exist, run `git init` and create an initial commit.

    Returns True if a new repo was initialized, False if one already existed.
    Raises GitError on failure.
    """
    if (project_root / ".git").is_dir():
        return False

    _run_git(["init"], cwd=project_root)
    _run_git(["config", "user.email", "shipyard@localhost"], cwd=project_root)
    _run_git(["config", "user.name", "Shipyard"], cwd=project_root)

    gitkeep = project_root / ".gitkeep"
    gitkeep.touch()
    _run_git(["add", ".gitkeep"], cwd=project_root)
    _run_git(["commit", "-m", "shipyard: initial commit"], cwd=project_root)
    return True


def git_commit(file_path: str, project_root: Path, message: str) -> str:
    """
    Stage and commit a single file.

    Args:
        file_path: Path to the file to commit (relative to project_root or absolute)
        project_root: Root directory of the git repo
        message: Commit message (will be prefixed with "shipyard: ")

    Returns:
        The commit hash (short form, 7 chars)

    Raises:
        GitError if git add or git commit fails
    """
    resolved = Path(file_path)
    if resolved.is_absolute():
        resolved = resolved.relative_to(project_root)

    _run_git(["add", str(resolved)], cwd=project_root)
    _run_git(["commit", "-m", f"shipyard: {message}"], cwd=project_root)
    return git_get_current_hash(project_root)


def git_commit_files(file_paths: list[str], project_root: Path, message: str) -> str:
    """
    Stage and commit multiple files in a single commit.
    Used by edit_file_multi for atomic batch commits.

    Returns the commit hash (short form).
    Raises GitError on failure.
    """
    for file_path in file_paths:
        resolved = Path(file_path)
        if resolved.is_absolute():
            resolved = resolved.relative_to(project_root)
        _run_git(["add", str(resolved)], cwd=project_root)

    _run_git(["commit", "-m", f"shipyard: {message}"], cwd=project_root)
    return git_get_current_hash(project_root)


def git_revert_last(project_root: Path, n: int = 1) -> None:
    """
    Revert the last n commits. Used for rollback on validation failure.

    Creates a new revert commit (does not rewrite history).
    Raises GitError on failure.
    """
    _run_git(["revert", "--no-commit", f"HEAD~{n}..HEAD"], cwd=project_root)
    _run_git(["commit", "-m", f"shipyard: revert {n} commit(s)"], cwd=project_root)


def git_get_current_hash(project_root: Path) -> str:
    """
    Return the current HEAD commit hash (short form).
    Useful for tracking state before/after operations.
    """
    result = _run_git(["rev-parse", "--short", "HEAD"], cwd=project_root)
    return result.stdout.strip()


def is_git_repo(project_root: Path) -> bool:
    """Check if the directory is inside a git repository."""
    try:
        _run_git(["rev-parse", "--is-inside-work-tree"], cwd=project_root)
        return True
    except GitError:
        return False
