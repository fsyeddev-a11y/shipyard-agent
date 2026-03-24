from pathlib import Path

from pydantic import BaseModel, Field

from shipyard.edit_engine.git import git_commit


class CreateFileInput(BaseModel):
    file_path: str = Field(description="Path for the new file (relative to project root)")
    content: str = Field(description="Content to write to the file")


async def create_file(
    file_path: str,
    content: str,
    project_root: Path | None = None,
) -> str:
    """
    Create a new file with the given content.

    - If file already exists, return error (don't overwrite)
    - Create parent directories if they don't exist
    - Git commit the new file
    """
    try:
        resolved = Path(file_path)
        if not resolved.is_absolute() and project_root:
            resolved = project_root / resolved

        if resolved.exists():
            return f"✗ File already exists: {file_path}"

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")

        line_count = content.count("\n") + (0 if content.endswith("\n") else 1)

        commit_hash = git_commit(file_path, project_root, f"create: {file_path}")
        return f"✓ Created {file_path} ({line_count} lines, commit: {commit_hash})"

    except Exception as e:
        return f"✗ Error creating {file_path}: {e}"
