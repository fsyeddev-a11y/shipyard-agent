from pathlib import Path

from pydantic import BaseModel, Field

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
# Note: .shipyard is NOT skipped — agent needs access to specs/, context/, and notes/
# Only .shipyard/sessions/ generates noise (JSONL logs) but that's manageable


class ListFilesInput(BaseModel):
    directory: str = Field(default=".", description="Directory to list (relative to project root)")
    depth: int = Field(default=3, description="Maximum depth to traverse")


async def list_files(
    directory: str = ".",
    depth: int = 3,
    project_root: Path | None = None,
) -> str:
    """
    List files in a directory tree.

    Respects depth limit, skips hidden/generated directories.
    """
    try:
        resolved = Path(directory)
        if not resolved.is_absolute() and project_root:
            resolved = project_root / resolved

        if not resolved.is_dir():
            return f"✗ Directory not found: {directory}"

        lines: list[str] = []
        _walk(resolved, depth, 0, lines)

        if not lines:
            return f"(empty directory: {directory})"
        return "\n".join(lines)

    except Exception as e:
        return f"✗ Error listing {directory}: {e}"


def _walk(path: Path, max_depth: int, current_depth: int, lines: list[str]) -> None:
    """Recursively build tree listing."""
    if current_depth >= max_depth:
        return

    indent = "  " * current_depth

    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return

    for entry in entries:
        if entry.name in SKIP_DIRS:
            continue
        if entry.is_dir():
            lines.append(f"{indent}{entry.name}/")
            _walk(entry, max_depth, current_depth + 1, lines)
        else:
            lines.append(f"{indent}{entry.name}")
