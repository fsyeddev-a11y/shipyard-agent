# Spec 02: Unified Diff Computation and Verification

## Objective
Create `shipyard/edit_engine/diff.py` — functions to compute unified diffs between file versions, parse diff hunks, and verify that all changes fall within the expected anchor span. This is the guardrail that ensures edits are truly surgical.

## Dependencies
- Phase 1 complete (project structure exists)

## File: `shipyard/edit_engine/diff.py`

### Data Structures

```python
from dataclasses import dataclass


@dataclass
class DiffHunk:
    """A single hunk from a unified diff."""
    old_start: int      # starting line in original file (1-based)
    old_count: int      # number of lines from original
    new_start: int      # starting line in modified file (1-based)
    new_count: int      # number of lines in modified
    lines_added: int    # count of "+" lines
    lines_removed: int  # count of "-" lines


@dataclass
class VerificationResult:
    """Result of diff verification against anchor boundaries."""
    passed: bool
    reason: str | None = None  # explanation if failed
```

### Functions to Implement

```python
import difflib


def compute_unified_diff(
    original: str,
    modified: str,
    file_path: str = "file",
    context_lines: int = 3,
) -> str:
    """
    Compute a unified diff between original and modified content.

    Uses difflib.unified_diff. Returns the diff as a single string.
    file_path is used in the --- / +++ headers.
    context_lines controls how many surrounding lines are shown (default 3).

    Returns empty string if contents are identical.
    """


def parse_hunks(diff: str) -> list[DiffHunk]:
    """
    Parse a unified diff string into a list of DiffHunk objects.

    Parses @@ -old_start,old_count +new_start,new_count @@ header lines.
    For each hunk, counts the "+" and "-" lines.

    Handle edge cases:
    - @@ -1 +1 @@ (count omitted means 1)
    - @@ -0,0 +1,5 @@ (new file, old is empty)
    """


def verify_diff(
    diff: str,
    anchor_start: int,
    anchor_end: int,
    max_changed_lines: int = 100,
) -> VerificationResult:
    """
    Verify that all diff hunks fall within the anchor span.

    Args:
        diff: unified diff string
        anchor_start: start line of the anchor in the ORIGINAL file (0-based)
        anchor_end: end line of the anchor in the ORIGINAL file (0-based)
        max_changed_lines: maximum total changed lines allowed

    Verification rules:
    1. All hunks must fall within [anchor_start, anchor_end] range
       - Uses OLD-FILE line numbers (not new-file, since new file shifts)
       - Hunk's old_start (converted to 0-based) must be >= anchor_start
       - Hunk's old_start + old_count - 1 (converted to 0-based) must be <= anchor_end
    2. Total changed lines (added + removed across all hunks) must be <= max_changed_lines
    3. No unexpected deletions: lines removed should only be within the anchor region
       (this is implicitly checked by rule 1)

    Returns VerificationResult with passed=True or passed=False with reason.
    """


def diff_summary(diff: str) -> str:
    """
    Produce a one-line summary of the diff: "+N -M lines".
    Used for commit messages and logging.
    """
```

### Implementation Notes

- `compute_unified_diff` uses `difflib.unified_diff` with `lineterm=""` to avoid double newlines. Split input by lines first.
- `parse_hunks` regex for the @@ line: `r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@'`
  - When count is omitted, it defaults to 1
  - old_start and new_start are **1-based** in the diff format
- `verify_diff` needs to convert from 1-based (diff format) to 0-based (how the engine records anchor positions). So: `hunk_start_0based = hunk.old_start - 1`
- The verification uses **old-file line numbers** because the new file's line numbers shift when the replacement changes block size. This is a critical design decision from the requirements.
- `diff_summary` counts total "+" and "-" lines across all hunks

### Edge Cases
- Identical content → empty diff → verification passes trivially
- Single-line change → one hunk with 1 added, 1 removed
- Anchor at the very start of file (line 0) or very end
- Large replacement that changes block size significantly — old-file coordinates still valid

## Acceptance Criteria
- [ ] `compute_unified_diff` produces standard unified diff output
- [ ] `compute_unified_diff` returns empty string for identical content
- [ ] `parse_hunks` correctly parses @@ headers with and without counts
- [ ] `parse_hunks` correctly counts added/removed lines per hunk
- [ ] `verify_diff` passes when all hunks are within anchor span
- [ ] `verify_diff` fails when a hunk falls outside anchor span
- [ ] `verify_diff` fails when total changed lines exceed threshold
- [ ] `verify_diff` returns descriptive reason on failure
- [ ] `diff_summary` returns "+N -M lines" format
