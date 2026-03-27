# Spec 04: Edit Engine Test Suite

## Objective
Create `tests/test_edit_engine.py` — comprehensive tests for the entire edit engine. This is the most critical test file in the project. The edit engine is deterministic code that MUST be correct.

## Dependencies
- Specs 01-03 (normalize, diff, engine) must be complete

## File: `tests/test_edit_engine.py`

### Test Structure

Use `tmp_path` fixture for all tests. Each test that involves `apply_edit` or `apply_edit_multi` needs a git repo, so create a shared fixture:

```python
import pytest
from pathlib import Path
from shipyard.edit_engine.engine import apply_edit, apply_edit_multi, EditResult
from shipyard.edit_engine.diff import compute_unified_diff, parse_hunks, verify_diff, diff_summary
from shipyard.edit_engine.normalize import detect_style, normalize_content, normalize_for_edit, FileStyle
from shipyard.edit_engine.git import git_init_if_needed


@pytest.fixture
def project(tmp_path):
    """Create a temporary git repo with a sample file."""
    git_init_if_needed(tmp_path)
    return tmp_path


def _write(project: Path, name: str, content: str) -> str:
    """Helper: write a file and return its path relative to project."""
    f = project / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    return name
```

### Tests to Implement

#### Normalization Tests

```python
def test_detect_style_spaces_4():
    """File with 4-space indentation detected correctly."""

def test_detect_style_spaces_2():
    """File with 2-space indentation detected correctly."""

def test_detect_style_tabs():
    """File with tab indentation detected correctly."""

def test_detect_style_crlf():
    """File with \\r\\n line endings detected correctly."""

def test_detect_style_empty():
    """Empty file returns sensible defaults (4 spaces, \\n)."""

def test_normalize_spaces_to_tabs():
    """Content with spaces normalized to tabs when file uses tabs."""

def test_normalize_tabs_to_spaces():
    """Content with tabs normalized to spaces when file uses spaces."""

def test_normalize_crlf_to_lf():
    """Content with \\r\\n normalized to \\n when file uses \\n."""

def test_normalize_trailing_whitespace_stripped():
    """Trailing spaces on lines are removed."""

def test_normalize_final_newline():
    """Content always ends with exactly one newline."""

def test_normalize_already_matching():
    """Content that already matches file style is returned mostly unchanged."""
```

#### Diff Tests

```python
def test_compute_diff_simple_change():
    """Simple one-line change produces a valid unified diff."""

def test_compute_diff_identical():
    """Identical content produces empty diff string."""

def test_compute_diff_multiline():
    """Multi-line addition/removal produces correct diff."""

def test_parse_hunks_single():
    """Single hunk parsed with correct line numbers and counts."""

def test_parse_hunks_multiple():
    """Multiple hunks parsed correctly."""

def test_parse_hunks_omitted_count():
    """@@ -1 +1 @@ (count omitted, defaults to 1) parsed correctly."""

def test_verify_diff_within_anchor():
    """Diff with all hunks inside anchor span passes verification."""

def test_verify_diff_outside_anchor():
    """Diff with hunk outside anchor span fails verification with reason."""

def test_verify_diff_exceeds_threshold():
    """Diff exceeding max_changed_lines fails verification."""

def test_verify_diff_empty():
    """Empty diff passes verification trivially."""

def test_diff_summary_format():
    """diff_summary returns '+N -M lines' format."""
```

#### Core Engine Tests — apply_edit

```python
def test_edit_anchor_found_succeeds(project):
    """edit with unique anchor → replacement applied, diff returned, git commit created."""
    content = "line1\\nline2\\nline3\\nline4\\nline5\\n"
    name = _write(project, "test.txt", content)
    result = apply_edit(name, "line2\\nline3", "line2_modified\\nline3_modified", project, "test edit")
    assert result.success is True
    assert result.diff is not None
    assert result.commit_hash is not None
    # Verify file on disk
    assert "line2_modified" in (project / name).read_text()

def test_edit_anchor_not_found(project):
    """edit with non-existent old_content → error with file preview."""
    name = _write(project, "test.txt", "hello world\\n")
    result = apply_edit(name, "does not exist", "replacement", project)
    assert result.success is False
    assert result.error == "anchor_not_found"
    assert result.file_context is not None
    # File unchanged
    assert (project / name).read_text() == "hello world\\n"

def test_edit_anchor_ambiguous(project):
    """edit where old_content appears twice → ambiguous error."""
    name = _write(project, "test.txt", "foo\\nbar\\nfoo\\nbar\\n")
    result = apply_edit(name, "foo", "baz", project)
    assert result.success is False
    assert result.error == "ambiguous_anchor"

def test_edit_file_not_found(project):
    """edit on non-existent file → file_not_found error."""
    result = apply_edit("nonexistent.txt", "old", "new", project)
    assert result.success is False
    assert result.error == "file_not_found"

def test_edit_file_not_written_on_failure(project):
    """On any error, the original file must be unchanged on disk."""
    content = "aaa\\nbbb\\nccc\\n"
    name = _write(project, "test.txt", content)
    # Trigger ambiguous anchor
    name2 = _write(project, "test2.txt", "dup\\ndup\\n")
    apply_edit("test2.txt", "dup", "changed", project)
    assert (project / "test2.txt").read_text() == "dup\\ndup\\n"

def test_edit_git_commit_created(project):
    """Successful edit creates a git commit with 'shipyard: edit:' prefix."""
    name = _write(project, "test.txt", "original content\\n")
    result = apply_edit(name, "original content", "new content", project, "update text")
    assert result.success is True
    assert result.commit_hash is not None
    # Verify commit exists via git log
    import subprocess
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=project, capture_output=True, text=True)
    assert "shipyard:" in log.stdout

def test_edit_whitespace_normalized(project):
    """new_content whitespace is normalized to match file conventions."""
    # File uses 4-space indent
    content = "def foo():\\n    return 1\\n"
    name = _write(project, "test.py", content)
    # new_content uses 2-space indent (simulating LLM output)
    result = apply_edit(name, "    return 1", "    return 2", project, "fix return")
    assert result.success is True

def test_edit_large_file(project):
    """Edit works correctly on files with 500+ lines."""
    lines = [f"line {i}" for i in range(600)]
    content = "\\n".join(lines) + "\\n"
    name = _write(project, "large.txt", content)
    result = apply_edit(name, "line 300", "line 300 modified", project, "edit line 300")
    assert result.success is True
    assert "line 300 modified" in (project / name).read_text()

def test_edit_sequential_same_file(project):
    """Two sequential edits to the same file: second sees the updated content."""
    content = "aaa\\nbbb\\nccc\\n"
    name = _write(project, "test.txt", content)
    r1 = apply_edit(name, "aaa", "xxx", project, "first edit")
    assert r1.success is True
    r2 = apply_edit(name, "xxx", "yyy", project, "second edit")
    assert r2.success is True
    assert (project / name).read_text() == "yyy\\nbbb\\nccc\\n"
```

#### Core Engine Tests — apply_edit_multi

```python
def test_edit_multi_all_succeed(project):
    """edit_multi with all valid anchors → all applied, single commit."""
    content = "aaa\\nbbb\\nccc\\nddd\\n"
    name = _write(project, "test.txt", content)
    edits = [
        {"old_content": "aaa", "new_content": "xxx"},
        {"old_content": "ccc", "new_content": "zzz"},
    ]
    result = apply_edit_multi(name, edits, project, "multi edit")
    assert result.success is True
    text = (project / name).read_text()
    assert "xxx" in text
    assert "zzz" in text
    assert result.commit_hash is not None

def test_edit_multi_one_fails_none_applied(project):
    """edit_multi where one anchor is invalid → no edits applied at all."""
    content = "aaa\\nbbb\\nccc\\n"
    name = _write(project, "test.txt", content)
    edits = [
        {"old_content": "aaa", "new_content": "xxx"},
        {"old_content": "DOES_NOT_EXIST", "new_content": "yyy"},
    ]
    result = apply_edit_multi(name, edits, project, "should fail")
    assert result.success is False
    # File unchanged
    assert (project / name).read_text() == "aaa\\nbbb\\nccc\\n"

def test_edit_multi_reverse_order(project):
    """edit_multi applies edits bottom-to-top so positions don't drift."""
    content = "line1\\nline2\\nline3\\nline4\\nline5\\n"
    name = _write(project, "test.txt", content)
    edits = [
        {"old_content": "line1", "new_content": "LINE_ONE\\nEXTRA_LINE"},
        {"old_content": "line5", "new_content": "LINE_FIVE"},
    ]
    result = apply_edit_multi(name, edits, project, "reverse order test")
    assert result.success is True
    text = (project / name).read_text()
    assert "LINE_ONE" in text
    assert "EXTRA_LINE" in text
    assert "LINE_FIVE" in text

def test_edit_multi_ambiguous_anchor(project):
    """edit_multi with ambiguous anchor fails validation, no edits applied."""
    content = "dup\\nother\\ndup\\n"
    name = _write(project, "test.txt", content)
    edits = [
        {"old_content": "dup", "new_content": "unique"},
        {"old_content": "other", "new_content": "changed"},
    ]
    result = apply_edit_multi(name, edits, project, "should fail")
    assert result.success is False
    assert result.error == "ambiguous_anchor"
    assert (project / name).read_text() == "dup\\nother\\ndup\\n"

def test_edit_multi_single_commit(project):
    """edit_multi produces exactly one git commit for the batch."""
    content = "aaa\\nbbb\\nccc\\n"
    name = _write(project, "test.txt", content)
    import subprocess
    before = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=project, capture_output=True, text=True)
    before_count = int(before.stdout.strip())

    edits = [
        {"old_content": "aaa", "new_content": "xxx"},
        {"old_content": "ccc", "new_content": "zzz"},
    ]
    apply_edit_multi(name, edits, project, "batch")

    after = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=project, capture_output=True, text=True)
    after_count = int(after.stdout.strip())

    assert after_count == before_count + 1  # exactly one new commit
```

### Running the Tests

```bash
pytest tests/test_edit_engine.py -v
```

All tests must pass. If any test requires adjusting the implementation (e.g., edge cases in normalization or diff verification), fix the implementation — the tests define the contract.

## Acceptance Criteria
- [ ] All normalization tests pass
- [ ] All diff tests pass
- [ ] All apply_edit tests pass
- [ ] All apply_edit_multi tests pass
- [ ] No test is skipped or xfailed
- [ ] `pytest tests/test_edit_engine.py -v` shows all green
