# Spec 03: Git Helpers

## Objective
Create `shipyard/edit_engine/git.py` — deterministic git operations used by the edit engine. These are called after every validated edit for auto-commit, and for rollback on validation failure.

## Dependencies
- Spec 01 (project scaffolding) must be complete
- Spec 02 (config) must be complete

## File: `shipyard/edit_engine/git.py`

### Functions to Implement

```python
import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""
    pass


def git_init_if_needed(project_root: Path) -> bool:
    """
    Ensure the project directory is a git repo.
    If .git/ doesn't exist, run `git init` and create an initial commit.

    Returns True if a new repo was initialized, False if one already existed.
    Raises GitError on failure.
    """


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


def git_commit_files(file_paths: list[str], project_root: Path, message: str) -> str:
    """
    Stage and commit multiple files in a single commit.
    Used by edit_file_multi for atomic batch commits.

    Returns the commit hash (short form).
    Raises GitError on failure.
    """


def git_revert_last(project_root: Path, n: int = 1) -> None:
    """
    Revert the last n commits. Used for rollback on validation failure.

    Creates a new revert commit (does not rewrite history).
    Raises GitError on failure.
    """


def git_get_current_hash(project_root: Path) -> str:
    """
    Return the current HEAD commit hash (short form).
    Useful for tracking state before/after operations.
    """


def is_git_repo(project_root: Path) -> bool:
    """Check if the directory is inside a git repository."""


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """
    Internal helper to run a git command.

    Raises GitError with stderr content on non-zero exit code.
    All git commands should go through this helper.
    """
```

### Implementation Notes

- All git commands run via `subprocess.run` with `capture_output=True`, `text=True`
- The `_run_git` helper centralizes error handling — check `returncode`, raise `GitError` with `stderr` on failure
- `git_commit` prefixes the message: `f"shipyard: {message}"`
- `git_init_if_needed` should create an initial commit with message `"shipyard: initial commit"` (empty commit or commit a `.gitkeep`) so that `git revert` has something to work with
- `git_revert_last` uses `git revert --no-commit HEAD~{n}..HEAD` followed by `git commit -m "shipyard: revert {n} commit(s)"` — this creates a new commit rather than rewriting history
- All functions are synchronous (git operations are fast, no need for async)
- `file_path` in `git_commit` should be resolved relative to `project_root` before passing to git

### Test File: `tests/test_git_helpers.py`

Write tests using `tmp_path` fixture (pytest provides a temporary directory). Each test should:
1. Create a temp directory
2. Run `git_init_if_needed`
3. Create/modify files
4. Test the git operation

```python
# Tests to implement:

def test_git_init_creates_repo(tmp_path):
    """git_init_if_needed on a non-git dir creates .git/ and initial commit."""

def test_git_init_idempotent(tmp_path):
    """git_init_if_needed on an existing repo returns False, no error."""

def test_git_commit_single_file(tmp_path):
    """git_commit stages and commits a file, returns a commit hash."""

def test_git_commit_files_multiple(tmp_path):
    """git_commit_files commits multiple files in one commit."""

def test_git_revert_last_one(tmp_path):
    """git_revert_last(n=1) creates a revert commit undoing the last change."""

def test_git_revert_last_multiple(tmp_path):
    """git_revert_last(n=2) reverts the last two commits."""

def test_git_get_current_hash(tmp_path):
    """git_get_current_hash returns a 7-char hash string."""

def test_is_git_repo_true(tmp_path):
    """is_git_repo returns True for an initialized repo."""

def test_is_git_repo_false(tmp_path):
    """is_git_repo returns False for a plain directory."""

def test_git_commit_error_on_untracked(tmp_path):
    """git_commit on a file that doesn't exist raises GitError."""
```

## Acceptance Criteria
- [ ] All functions importable: `from shipyard.edit_engine.git import git_commit, git_init_if_needed, ...`
- [ ] `git_init_if_needed` creates a repo with an initial commit
- [ ] `git_commit` creates a commit with the "shipyard: " prefix
- [ ] `git_revert_last` creates revert commits (non-destructive)
- [ ] `GitError` raised on failures with descriptive messages
- [ ] All tests pass: `pytest tests/test_git_helpers.py -v`
