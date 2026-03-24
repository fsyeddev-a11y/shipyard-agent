from pathlib import Path

from pydantic import BaseModel, Field

from shipyard.edit_engine.engine import apply_edit as _apply_edit, apply_edit_multi as _apply_edit_multi, EditResult


class EditFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to edit (relative to project root)")
    old_content: str = Field(description="The exact text to find and replace. Must match exactly once in the file.")
    new_content: str = Field(description="The replacement text")
    description: str = Field(default="", description="Brief description of the change (used in commit message)")


class EditFileMultiInput(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    edits: list[dict] = Field(description="List of {old_content, new_content} pairs to apply atomically")
    description: str = Field(default="", description="Brief description of the changes")


def _format_result(result: EditResult, file_path: str) -> str:
    """Format an EditResult into a human-readable string."""
    if result.success:
        return f"✓ Edited {file_path}: {result.diff_summary} (commit: {result.commit_hash})"

    msg = f"✗ {result.error}: {result.error_detail}"
    if result.file_context:
        msg += f"\n\nFile content:\n{result.file_context}"
    return msg


async def edit_file(
    file_path: str,
    old_content: str,
    new_content: str,
    description: str = "",
    project_root: Path | None = None,
) -> str:
    """
    Make a surgical edit to a file using anchor-based replacement.

    Delegates to edit_engine.apply_edit(). Returns a human-readable summary string.
    """
    try:
        result = _apply_edit(file_path, old_content, new_content, project_root, description)
        return _format_result(result, file_path)
    except Exception as e:
        return f"✗ Unexpected error editing {file_path}: {e}"


async def edit_file_multi(
    file_path: str,
    edits: list[dict],
    description: str = "",
    project_root: Path | None = None,
) -> str:
    """
    Apply multiple edits to a single file atomically.

    Delegates to edit_engine.apply_edit_multi(). Same return format as edit_file.
    """
    try:
        result = _apply_edit_multi(file_path, edits, project_root, description)
        return _format_result(result, file_path)
    except Exception as e:
        return f"✗ Unexpected error editing {file_path}: {e}"
