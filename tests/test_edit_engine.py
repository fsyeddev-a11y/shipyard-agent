import subprocess

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


# ============================================================
# Normalization Tests
# ============================================================


def test_detect_style_spaces_4():
    """File with 4-space indentation detected correctly."""
    content = "def foo():\n    return 1\n    pass\n"
    style = detect_style(content)
    assert style.indent_char == " "
    assert style.indent_size == 4
    assert style.line_ending == "\n"


def test_detect_style_spaces_2():
    """File with 2-space indentation detected correctly."""
    content = "function foo() {\n  return 1;\n  console.log();\n}\n"
    style = detect_style(content)
    assert style.indent_char == " "
    assert style.indent_size == 2


def test_detect_style_tabs():
    """File with tab indentation detected correctly."""
    content = "def foo():\n\treturn 1\n\tpass\n"
    style = detect_style(content)
    assert style.indent_char == "\t"
    assert style.indent_size == 0


def test_detect_style_crlf():
    """File with \\r\\n line endings detected correctly."""
    content = "line1\r\nline2\r\nline3\r\n"
    style = detect_style(content)
    assert style.line_ending == "\r\n"


def test_detect_style_empty():
    """Empty file returns sensible defaults (4 spaces, \\n)."""
    style = detect_style("")
    assert style.indent_char == " "
    assert style.indent_size == 4
    assert style.line_ending == "\n"


def test_normalize_spaces_to_tabs():
    """Content with spaces normalized to tabs when file uses tabs."""
    file_style = FileStyle(indent_char="\t", indent_size=0, line_ending="\n")
    content = "def foo():\n    return 1\n"
    result = normalize_content(content, file_style)
    assert "\treturn 1" in result


def test_normalize_tabs_to_spaces():
    """Content with tabs normalized to spaces when file uses spaces."""
    file_style = FileStyle(indent_char=" ", indent_size=4, line_ending="\n")
    content = "def foo():\n\treturn 1\n"
    result = normalize_content(content, file_style)
    assert "    return 1" in result


def test_normalize_crlf_to_lf():
    """Content with \\r\\n normalized to \\n when file uses \\n."""
    file_style = FileStyle(indent_char=" ", indent_size=4, line_ending="\n")
    content = "line1\r\nline2\r\n"
    result = normalize_content(content, file_style)
    assert "\r\n" not in result
    assert result.endswith("\n")


def test_normalize_trailing_whitespace_stripped():
    """Trailing spaces on lines are removed."""
    file_style = FileStyle(indent_char=" ", indent_size=4, line_ending="\n")
    content = "hello   \nworld  \n"
    result = normalize_content(content, file_style)
    assert "hello\n" in result
    assert "world\n" in result


def test_normalize_final_newline():
    """Content always ends with exactly one newline."""
    file_style = FileStyle(indent_char=" ", indent_size=4, line_ending="\n")
    # No trailing newline
    result1 = normalize_content("hello", file_style)
    assert result1.endswith("\n")
    assert not result1.endswith("\n\n")
    # Multiple trailing newlines
    result2 = normalize_content("hello\n\n\n", file_style)
    assert result2.endswith("\n")
    assert not result2.endswith("\n\n")


def test_normalize_already_matching():
    """Content that already matches file style is returned mostly unchanged."""
    file_style = FileStyle(indent_char=" ", indent_size=4, line_ending="\n")
    content = "def foo():\n    return 1\n"
    result = normalize_content(content, file_style)
    assert result == content


# ============================================================
# Diff Tests
# ============================================================


def test_compute_diff_simple_change():
    """Simple one-line change produces a valid unified diff."""
    original = "line1\nline2\nline3\n"
    modified = "line1\nline2_changed\nline3\n"
    diff = compute_unified_diff(original, modified, "test.txt")
    assert diff != ""
    assert "line2" in diff
    assert "line2_changed" in diff


def test_compute_diff_identical():
    """Identical content produces empty diff string."""
    content = "line1\nline2\n"
    diff = compute_unified_diff(content, content, "test.txt")
    assert diff == ""


def test_compute_diff_multiline():
    """Multi-line addition/removal produces correct diff."""
    original = "aaa\nbbb\nccc\n"
    modified = "aaa\nbbb\ninserted\nccc\nextra\n"
    diff = compute_unified_diff(original, modified, "test.txt")
    assert "+inserted" in diff
    assert "+extra" in diff


def test_parse_hunks_single():
    """Single hunk parsed with correct line numbers and counts."""
    original = "aaa\nbbb\nccc\n"
    modified = "aaa\nBBB\nccc\n"
    diff = compute_unified_diff(original, modified)
    hunks = parse_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0].lines_added >= 1
    assert hunks[0].lines_removed >= 1


def test_parse_hunks_multiple():
    """Multiple hunks parsed correctly."""
    # Create content with changes far apart to produce multiple hunks
    lines = [f"line{i}" for i in range(30)]
    original = "\n".join(lines) + "\n"
    modified_lines = lines.copy()
    modified_lines[2] = "CHANGED2"
    modified_lines[27] = "CHANGED27"
    modified = "\n".join(modified_lines) + "\n"
    diff = compute_unified_diff(original, modified)
    hunks = parse_hunks(diff)
    assert len(hunks) >= 2


def test_parse_hunks_omitted_count():
    """@@ -1 +1 @@ (count omitted, defaults to 1) parsed correctly."""
    diff = "--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n"
    hunks = parse_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0].old_start == 1
    assert hunks[0].old_count == 1
    assert hunks[0].new_start == 1
    assert hunks[0].new_count == 1


def test_verify_diff_within_anchor():
    """Diff with all hunks inside anchor span passes verification."""
    original = "aaa\nbbb\nccc\nddd\n"
    modified = "aaa\nBBB\nccc\nddd\n"
    diff = compute_unified_diff(original, modified)
    result = verify_diff(diff, anchor_start=0, anchor_end=3)
    assert result.passed is True


def test_verify_diff_outside_anchor():
    """Diff with hunk outside anchor span fails verification with reason."""
    original = "aaa\nbbb\nccc\nddd\n"
    modified = "aaa\nBBB\nccc\nddd\n"
    diff = compute_unified_diff(original, modified)
    # Set anchor to only line 2-3, but the hunk context may include line 0
    result = verify_diff(diff, anchor_start=2, anchor_end=3)
    assert result.passed is False
    assert result.reason is not None


def test_verify_diff_exceeds_threshold():
    """Diff exceeding max_changed_lines fails verification."""
    lines = [f"line{i}" for i in range(20)]
    original = "\n".join(lines) + "\n"
    modified_lines = [f"CHANGED{i}" for i in range(20)]
    modified = "\n".join(modified_lines) + "\n"
    diff = compute_unified_diff(original, modified)
    result = verify_diff(diff, anchor_start=0, anchor_end=19, max_changed_lines=5)
    assert result.passed is False
    assert "exceeds" in result.reason


def test_verify_diff_empty():
    """Empty diff passes verification trivially."""
    result = verify_diff("", anchor_start=0, anchor_end=10)
    assert result.passed is True


def test_diff_summary_format():
    """diff_summary returns '+N -M lines' format."""
    original = "aaa\nbbb\nccc\n"
    modified = "aaa\nBBB\nccc\nextra\n"
    diff = compute_unified_diff(original, modified)
    summary = diff_summary(diff)
    assert summary.startswith("+")
    assert "-" in summary
    assert "lines" in summary


# ============================================================
# Core Engine Tests — apply_edit
# ============================================================


def test_edit_anchor_found_succeeds(project):
    """edit with unique anchor -> replacement applied, diff returned, git commit created."""
    content = "line1\nline2\nline3\nline4\nline5\n"
    name = _write(project, "test.txt", content)
    result = apply_edit(name, "line2\nline3", "line2_modified\nline3_modified", project, "test edit")
    assert result.success is True
    assert result.diff is not None
    assert result.commit_hash is not None
    # Verify file on disk
    assert "line2_modified" in (project / name).read_text()


def test_edit_anchor_not_found(project):
    """edit with non-existent old_content -> error with file preview."""
    name = _write(project, "test.txt", "hello world\n")
    result = apply_edit(name, "does not exist", "replacement", project)
    assert result.success is False
    assert result.error == "anchor_not_found"
    assert result.file_context is not None
    # File unchanged
    assert (project / name).read_text() == "hello world\n"


def test_edit_anchor_ambiguous(project):
    """edit where old_content appears twice -> ambiguous error."""
    name = _write(project, "test.txt", "foo\nbar\nfoo\nbar\n")
    result = apply_edit(name, "foo", "baz", project)
    assert result.success is False
    assert result.error == "ambiguous_anchor"


def test_edit_file_not_found(project):
    """edit on non-existent file -> file_not_found error."""
    result = apply_edit("nonexistent.txt", "old", "new", project)
    assert result.success is False
    assert result.error == "file_not_found"


def test_edit_file_not_written_on_failure(project):
    """On any error, the original file must be unchanged on disk."""
    name2 = _write(project, "test2.txt", "dup\ndup\n")
    apply_edit("test2.txt", "dup", "changed", project)
    assert (project / "test2.txt").read_text() == "dup\ndup\n"


def test_edit_git_commit_created(project):
    """Successful edit creates a git commit with 'shipyard: edit:' prefix."""
    name = _write(project, "test.txt", "original content\n")
    result = apply_edit(name, "original content", "new content", project, "update text")
    assert result.success is True
    assert result.commit_hash is not None
    # Verify commit exists via git log
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=project, capture_output=True, text=True)
    assert "shipyard:" in log.stdout


def test_edit_whitespace_normalized(project):
    """new_content whitespace is normalized to match file conventions."""
    # File uses 4-space indent
    content = "def foo():\n    return 1\n"
    name = _write(project, "test.py", content)
    # new_content uses 4-space indent (matching)
    result = apply_edit(name, "    return 1", "    return 2", project, "fix return")
    assert result.success is True


def test_edit_large_file(project):
    """Edit works correctly on files with 500+ lines."""
    lines = [f"line {i}" for i in range(600)]
    content = "\n".join(lines) + "\n"
    name = _write(project, "large.txt", content)
    result = apply_edit(name, "line 300", "line 300 modified", project, "edit line 300")
    assert result.success is True
    assert "line 300 modified" in (project / name).read_text()


def test_edit_sequential_same_file(project):
    """Two sequential edits to the same file: second sees the updated content."""
    content = "aaa\nbbb\nccc\n"
    name = _write(project, "test.txt", content)
    r1 = apply_edit(name, "aaa", "xxx", project, "first edit")
    assert r1.success is True
    r2 = apply_edit(name, "xxx", "yyy", project, "second edit")
    assert r2.success is True
    assert (project / name).read_text() == "yyy\nbbb\nccc\n"


# ============================================================
# Core Engine Tests — apply_edit_multi
# ============================================================


def test_edit_multi_all_succeed(project):
    """edit_multi with all valid anchors -> all applied, single commit."""
    content = "aaa\nbbb\nccc\nddd\n"
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
    """edit_multi where one anchor is invalid -> no edits applied at all."""
    content = "aaa\nbbb\nccc\n"
    name = _write(project, "test.txt", content)
    edits = [
        {"old_content": "aaa", "new_content": "xxx"},
        {"old_content": "DOES_NOT_EXIST", "new_content": "yyy"},
    ]
    result = apply_edit_multi(name, edits, project, "should fail")
    assert result.success is False
    # File unchanged
    assert (project / name).read_text() == "aaa\nbbb\nccc\n"


def test_edit_multi_reverse_order(project):
    """edit_multi applies edits bottom-to-top so positions don't drift."""
    content = "line1\nline2\nline3\nline4\nline5\n"
    name = _write(project, "test.txt", content)
    edits = [
        {"old_content": "line1", "new_content": "LINE_ONE\nEXTRA_LINE"},
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
    content = "dup\nother\ndup\n"
    name = _write(project, "test.txt", content)
    edits = [
        {"old_content": "dup", "new_content": "unique"},
        {"old_content": "other", "new_content": "changed"},
    ]
    result = apply_edit_multi(name, edits, project, "should fail")
    assert result.success is False
    assert result.error == "ambiguous_anchor"
    assert (project / name).read_text() == "dup\nother\ndup\n"


def test_edit_multi_single_commit(project):
    """edit_multi produces exactly one git commit for the batch."""
    content = "aaa\nbbb\nccc\n"
    name = _write(project, "test.txt", content)
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
