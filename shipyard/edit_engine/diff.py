import difflib
import re
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


_HUNK_HEADER_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


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
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
        lineterm="",
    ))

    if not diff_lines:
        return ""

    return "\n".join(diff_lines)


def parse_hunks(diff: str) -> list[DiffHunk]:
    """
    Parse a unified diff string into a list of DiffHunk objects.

    Parses @@ -old_start,old_count +new_start,new_count @@ header lines.
    For each hunk, counts the "+" and "-" lines.
    """
    if not diff:
        return []

    hunks: list[DiffHunk] = []
    lines = diff.split("\n")

    i = 0
    while i < len(lines):
        match = _HUNK_HEADER_RE.match(lines[i])
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1

            added = 0
            removed = 0
            i += 1

            while i < len(lines):
                line = lines[i]
                if line.startswith("@@") or line.startswith("--- ") or line.startswith("+++ "):
                    break
                if line.startswith("+"):
                    added += 1
                elif line.startswith("-"):
                    removed += 1
                i += 1

            hunks.append(DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                lines_added=added,
                lines_removed=removed,
            ))
            continue

        i += 1

    return hunks


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

    Returns VerificationResult with passed=True or passed=False with reason.
    """
    if not diff:
        return VerificationResult(passed=True)

    hunks = parse_hunks(diff)
    if not hunks:
        return VerificationResult(passed=True)

    total_changed = 0

    for hunk in hunks:
        # Convert 1-based diff line numbers to 0-based
        hunk_start_0 = hunk.old_start - 1
        hunk_end_0 = hunk_start_0 + hunk.old_count - 1

        if hunk_start_0 < anchor_start:
            return VerificationResult(
                passed=False,
                reason=(
                    f"Hunk starts at line {hunk_start_0} (0-based) "
                    f"which is before anchor start {anchor_start}"
                ),
            )

        if hunk_end_0 > anchor_end:
            return VerificationResult(
                passed=False,
                reason=(
                    f"Hunk ends at line {hunk_end_0} (0-based) "
                    f"which is past anchor end {anchor_end}"
                ),
            )

        total_changed += hunk.lines_added + hunk.lines_removed

    if total_changed > max_changed_lines:
        return VerificationResult(
            passed=False,
            reason=(
                f"Total changed lines ({total_changed}) "
                f"exceeds maximum ({max_changed_lines})"
            ),
        )

    return VerificationResult(passed=True)


def diff_summary(diff: str) -> str:
    """
    Produce a one-line summary of the diff: "+N -M lines".
    Used for commit messages and logging.
    """
    hunks = parse_hunks(diff)
    total_added = sum(h.lines_added for h in hunks)
    total_removed = sum(h.lines_removed for h in hunks)
    return f"+{total_added} -{total_removed} lines"
