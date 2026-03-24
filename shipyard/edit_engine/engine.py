from dataclasses import dataclass
from pathlib import Path

from shipyard.edit_engine.normalize import normalize_for_edit, detect_style
from shipyard.edit_engine.diff import compute_unified_diff, verify_diff, diff_summary
from shipyard.edit_engine.git import git_commit


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
    1. Read file from disk
    2. Find old_content (anchor) — must match exactly once
    3. Normalize new_content to match file conventions
    4. Replace old_content with normalized new_content
    5. Compute and verify unified diff
    6. Write file and git commit on success
    """
    # Step 1: Read file
    try:
        original_content = _read_file(file_path, project_root)
    except FileNotFoundError:
        return EditResult(
            success=False,
            error="file_not_found",
            error_detail=f"{file_path} does not exist",
        )

    # Step 2: Find anchor
    count, start_line, end_line = _find_anchor(original_content, old_content)

    if count == 0:
        lines = original_content.splitlines(keepends=True)
        context = "".join(lines[:100])
        return EditResult(
            success=False,
            error="anchor_not_found",
            error_detail=f"old_content not found in {file_path}",
            file_context=context,
        )

    if count >= 2:
        return EditResult(
            success=False,
            error="ambiguous_anchor",
            error_detail=f"old_content found {count} times in {file_path}. Include more surrounding context.",
        )

    # Step 3: Normalize new_content to match file style
    normalized_new = normalize_for_edit(new_content, original_content)
    # Preserve trailing-newline parity with old_content (we're replacing a fragment, not a whole file)
    if not old_content.endswith("\n") and normalized_new.endswith("\n"):
        normalized_new = normalized_new.rstrip("\n")
    elif old_content.endswith("\n") and not normalized_new.endswith("\n"):
        style = detect_style(original_content)
        normalized_new += style.line_ending

    # Step 4: Replace
    modified_content = original_content.replace(old_content, normalized_new, 1)

    # Step 5: Compute and verify diff
    rel_path = _relative_path(file_path, project_root)
    context_lines = 3
    diff = compute_unified_diff(original_content, modified_content, file_path=rel_path, context_lines=context_lines)
    summary = diff_summary(diff) if diff else "+0 -0 lines"

    # Expand anchor boundaries by context lines to account for diff context
    total_lines = original_content.count("\n")
    verify_start = max(0, start_line - context_lines)
    verify_end = min(total_lines, end_line + context_lines)
    verification = verify_diff(diff, verify_start, verify_end, max_changed_lines)
    if not verification.passed:
        return EditResult(
            success=False,
            diff=diff,
            diff_summary=summary,
            error="verification_failed",
            error_detail=verification.reason,
        )

    # Step 6: Write and commit
    _write_file(file_path, project_root, modified_content)
    commit_hash = git_commit(
        file_path, project_root, f"edit: {rel_path} — {description}" if description else f"edit: {rel_path}"
    )

    return EditResult(
        success=True,
        diff=diff,
        diff_summary=summary,
        commit_hash=commit_hash,
    )


def apply_edit_multi(
    file_path: str,
    edits: list[dict],
    project_root: Path,
    description: str = "",
    max_changed_lines: int = 200,
) -> EditResult:
    """
    Atomic multi-edit function. Called by the edit_file_multi tool.

    Validates ALL anchors first (all-or-nothing), sorts by position descending
    (bottom-to-top), applies all replacements, then computes a single diff and
    makes a single git commit.
    """
    # Step 1: Read file
    try:
        original_content = _read_file(file_path, project_root)
    except FileNotFoundError:
        return EditResult(
            success=False,
            error="file_not_found",
            error_detail=f"{file_path} does not exist",
        )

    # Step 2: Validation pass — all-or-nothing
    validated: list[tuple[str, str, int]] = []  # (old_content, normalized_new, char_offset)

    for i, edit in enumerate(edits):
        old = edit["old_content"]
        new = edit["new_content"]

        count, start_line, end_line = _find_anchor(original_content, old)

        if count == 0:
            lines = original_content.splitlines(keepends=True)
            context = "".join(lines[:100])
            return EditResult(
                success=False,
                error="anchor_not_found",
                error_detail=f"Edit {i + 1}: old_content not found in {file_path}",
                file_context=context,
            )

        if count >= 2:
            return EditResult(
                success=False,
                error="ambiguous_anchor",
                error_detail=f"Edit {i + 1}: old_content found {count} times in {file_path}. Include more surrounding context.",
            )

        # Normalize new_content against original file style
        normalized_new = normalize_for_edit(new, original_content)
        # Preserve trailing-newline parity with old_content
        if not old.endswith("\n") and normalized_new.endswith("\n"):
            normalized_new = normalized_new.rstrip("\n")
        elif old.endswith("\n") and not normalized_new.endswith("\n"):
            style = detect_style(original_content)
            normalized_new += style.line_ending
        char_offset = original_content.index(old)
        validated.append((old, normalized_new, char_offset))

    # Step 3: Sort by character offset descending (bottom-to-top)
    validated.sort(key=lambda x: x[2], reverse=True)

    # Step 4: Apply all replacements bottom-to-top
    modified_content = original_content
    for old, new, _offset in validated:
        modified_content = modified_content.replace(old, new, 1)

    # Step 5: Compute and verify diff
    rel_path = _relative_path(file_path, project_root)
    diff = compute_unified_diff(original_content, modified_content, file_path=rel_path)
    summary = diff_summary(diff) if diff else "+0 -0 lines"

    # For multi-edit, verify against the full file span (0 to last line)
    total_lines = original_content.count("\n")
    verification = verify_diff(diff, 0, total_lines, max_changed_lines)
    if not verification.passed:
        return EditResult(
            success=False,
            diff=diff,
            diff_summary=summary,
            error="verification_failed",
            error_detail=verification.reason,
        )

    # Step 6: Write and commit
    _write_file(file_path, project_root, modified_content)
    commit_hash = git_commit(
        file_path, project_root,
        f"edit(multi): {rel_path} — {description}" if description else f"edit(multi): {rel_path}"
    )

    return EditResult(
        success=True,
        diff=diff,
        diff_summary=summary,
        commit_hash=commit_hash,
    )


def _find_anchor(content: str, anchor: str) -> tuple[int, int, int]:
    """
    Find anchor text in content.

    Returns: (count, start_line, end_line)
    - count: number of occurrences (0, 1, or 2+)
    - start_line: 0-based line number where anchor starts (valid only if count == 1)
    - end_line: 0-based line number where anchor ends (valid only if count == 1)
    """
    count = content.count(anchor)
    if count != 1:
        return (count, -1, -1)

    char_offset = content.index(anchor)
    start_line = content[:char_offset].count("\n")
    end_line = start_line + anchor.count("\n")
    return (count, start_line, end_line)


def _read_file(file_path: str, project_root: Path) -> str:
    """Read a file from disk. Resolve path relative to project_root if not absolute."""
    resolved = Path(file_path)
    if not resolved.is_absolute():
        resolved = project_root / resolved
    return resolved.read_text(encoding="utf-8")


def _write_file(file_path: str, project_root: Path, content: str) -> None:
    """Write content to a file on disk."""
    resolved = Path(file_path)
    if not resolved.is_absolute():
        resolved = project_root / resolved
    resolved.write_text(content, encoding="utf-8")


def _relative_path(file_path: str, project_root: Path) -> str:
    """Get a relative path string for display purposes."""
    resolved = Path(file_path)
    if resolved.is_absolute():
        try:
            return str(resolved.relative_to(project_root))
        except ValueError:
            return file_path
    return file_path
