from pathlib import Path
from pydantic import BaseModel, Field

from shipyard.edit_engine.git import git_commit


class DeleteFileInput(BaseModel):
    file_path: str = Field(description="File path to delete (relative to project root)")


async def delete_file(
    file_path: str,
    project_root: Path,
) -> str:
    """Delete a file. Auto-commits the deletion."""
    target = project_root / file_path

    if not target.exists():
        return f"✗ File not found: {file_path}"

    if target.is_dir():
        return f"✗ {file_path} is a directory, not a file. Use run_command with rm -rf to delete directories."

    target.unlink()

    try:
        import subprocess
        subprocess.run(["git", "add", "-A"], cwd=project_root, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"shipyard: delete {file_path}"],
            cwd=project_root, capture_output=True,
        )
    except Exception as e:
        return f"✓ Deleted {file_path} (git commit failed: {e})"

    return f"✓ Deleted {file_path}"
