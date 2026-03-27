import shutil
from pathlib import Path
from pydantic import BaseModel, Field

from shipyard.edit_engine.git import git_commit


class MoveFileInput(BaseModel):
    source: str = Field(description="Source file path (relative to project root)")
    destination: str = Field(description="Destination file path (relative to project root)")


async def move_file(
    source: str,
    destination: str,
    project_root: Path,
) -> str:
    """Move or rename a file. Creates parent directories if needed. Auto-commits."""
    src = project_root / source
    dst = project_root / destination

    if not src.exists():
        return f"✗ Source not found: {source}"

    if dst.exists():
        return f"✗ Destination already exists: {destination}"

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    try:
        git_commit_move(source, destination, project_root)
    except Exception as e:
        return f"✓ Moved {source} → {destination} (git commit failed: {e})"

    return f"✓ Moved {source} → {destination}"


def git_commit_move(source: str, destination: str, project_root: Path) -> None:
    """Stage both the delete and add, then commit."""
    import subprocess
    subprocess.run(["git", "add", "-A"], cwd=project_root, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"shipyard: move {source} → {destination}"],
        cwd=project_root, capture_output=True,
    )
