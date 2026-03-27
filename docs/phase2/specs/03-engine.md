# Spec 03: Core Edit Engine

## Objective
Create `shipyard/edit_engine/engine.py` — the core `apply_edit` and `apply_edit_multi` functions that tie together anchor matching, normalization, diff verification, and git auto-commit. This is the primary entry point used by the `edit_file` and `edit_file_multi` tools.

## Dependencies
- Spec 01 (normalize.py) must be complete
- Spec 02 (diff.py) must be complete
- Phase 1 git helpers (`shipyard/edit_engine/git.py`) must be available

## File: `shipyard/edit_engine/engine.py`

### Data Structures

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EditResult:
    """Result of an edit operation."""
    success: bool
    diff: str | None = None           # unified diff (always computed when possible)
    diff_summary: str | None = None   # "+N -M lines"
    commit_hash: str | None = None    # git commit hash on success
    error: str | None = None          # error type: "anchor_not_found", "ambiguous_anchor", "verification_failed"
    error_detail: str | None = None   # human-readable detail
    file_context: str | None = None   # returned on anchor errors for LLM retry context
```

### Functions to Implement

```python
def apply_edit(
    file_path: str,
    old_content: str,
    new_content: str,
    project_root: Path,
    description: str = "",
    max_changed_lines: int = 100,
) -> EditResult:
    """
    Core single-edit function. Called by the edit_file tool.
    Deterministic — no LLM calls.

    Steps:
    1. Read file from disk → original_content
    2. Find old_content in original_content
       - 0 matches → return error "anchor_not_found" with first ~100 lines as file_context
       - 2+ matches → return error "ambiguous_anchor" with match count
    3. Record anchor position: start_line and end_line (0-based) in original file
    4. Normalize new_content to match file conventions (via normalize_for_edit)
    5. Replace old_content with normalized new_content → modified_content
    6. Compute unified diff between original and modified
    7. Verify diff: all hunks within anchor span, changed lines under threshold
       - If verification fails → return error with diff and reason (do NOT write file)
    8. Write modified_content to disk
    9. Git commit with message: "edit: {file_path} — {description}"
    10. Return success with diff, summary, and commit hash

    Args:
        file_path: path to the file (relative to project_root or absolute)
        old_content: exact text to find and replace
        new_content: replacement text
        project_root: root of the git repo / project
        description: brief description for the commit message
        max_changed_lines: diff verification threshold

    Returns:
        EditResult with success=True/False and relevant details
    """


def apply_edit_multi(
    file_path: str,
    edits: list[dict],
    project_root: Path,
    description: str = "",
    max_changed_lines: int = 200,
) -> EditResult:
    """
    Atomic multi-edit function. Called by the edit_file_multi tool.

    Args:
        file_path: path to the file
        edits: list of {"old_content": str, "new_content": str} dicts
        project_root: root of the git repo / project
        description: brief description for the commit message
        max_changed_lines: diff verification threshold (higher default for multi)

    Steps:
    1. Read file from disk → original_content
    2. VALIDATION PASS (all-or-nothing):
       For each edit in the list:
       a. Find old_content in original_content
       b. If 0 matches → return error for that edit
       c. If 2+ matches → return error for that edit
       d. Record the anchor start position (character offset) for ordering
       If ANY edit fails validation, return error immediately. No edits applied.
    3. Sort edits by anchor position DESCENDING (bottom of file first)
       This ensures earlier replacements don't shift positions of later ones.
    4. Apply all replacements sequentially (bottom-to-top) → modified_content
    5. Normalize the full modified content's whitespace? No — normalize each
       new_content individually against the original file style BEFORE applying.
    6. Compute unified diff between original_content and final modified_content
    7. Verify diff (with higher threshold since multiple edits)
       - If verification fails → return error (do NOT write file)
    8. Write modified_content to disk
    9. Git commit with message: "edit(multi): {file_path} — {description}"
    10. Return success with combined diff, summary, and commit hash

    Returns:
        EditResult with success=True/False and relevant details
    """


def _find_anchor(content: str, anchor: str) -> tuple[int, int, int]:
    """
    Find anchor text in content.

    Returns: (count, start_line, end_line)
    - count: number of occurrences (0, 1, or 2+)
    - start_line: 0-based line number where anchor starts (valid only if count == 1)
    - end_line: 0-based line number where anchor ends (valid only if count == 1)
    """


def _read_file(file_path: str, project_root: Path) -> str:
    """Read a file from disk. Resolve path relative to project_root if not absolute."""


def _write_file(file_path: str, project_root: Path, content: str) -> None:
    """Write content to a file on disk."""
```

### Implementation Notes

- **File reading:** Resolve `file_path` relative to `project_root`. Read with UTF-8 encoding.
- **Anchor finding:** Use `str.count()` for occurrence check, `str.index()` for position. Convert character offset to line number by counting `\n` in `content[:offset]`.
- **Anchor end line:** `start_line + old_content.count('\n')`. The anchor span is inclusive: lines `[start_line, end_line]`.
- **Normalization happens BEFORE replacement** — normalize `new_content` against the original file, then substitute.
- **apply_edit_multi ordering:** After validating all anchors exist uniquely, find each anchor's character offset via `str.index()`, sort by offset descending, then apply replacements in that order. Since we go bottom-to-top, each `str.replace(old, new, 1)` won't affect the positions of anchors above it.
- **Git integration:** Import from `shipyard.edit_engine.git`. Call `git_commit` for single edits, `git_commit_files` for multi (though it's always one file, `git_commit` works fine).
- **File context on error:** When anchor is not found, return the first ~100 lines of the file (or first 3000 characters) so the LLM can see what's actually there and retry.
- **Ambiguous anchor error:** Include the match count in the error detail so the LLM knows to include more surrounding context.

### Error Responses
| Error | `error` field | `error_detail` | `file_context` |
|-------|--------------|----------------|----------------|
| Anchor not found | `"anchor_not_found"` | `"old_content not found in {file_path}"` | First ~100 lines |
| Ambiguous anchor | `"ambiguous_anchor"` | `"old_content found {N} times in {file_path}. Include more surrounding context."` | None |
| Diff verification fail | `"verification_failed"` | Reason from VerificationResult | None (diff is included) |
| File not found | `"file_not_found"` | `"{file_path} does not exist"` | None |

## Acceptance Criteria
- [ ] `apply_edit` succeeds on a simple single-anchor replacement
- [ ] `apply_edit` returns `anchor_not_found` with file context when old_content doesn't match
- [ ] `apply_edit` returns `ambiguous_anchor` when old_content matches 2+ times
- [ ] `apply_edit` returns `verification_failed` when diff has hunks outside anchor span
- [ ] `apply_edit` does NOT write the file on any error
- [ ] `apply_edit` creates a git commit on success
- [ ] `apply_edit` normalizes whitespace before applying
- [ ] `apply_edit_multi` validates all anchors before applying any
- [ ] `apply_edit_multi` applies edits bottom-to-top
- [ ] `apply_edit_multi` is atomic: if one anchor fails, no edits applied
- [ ] `apply_edit_multi` creates a single git commit for the batch
- [ ] `EditResult` contains all relevant fields (diff, summary, hash, errors)
