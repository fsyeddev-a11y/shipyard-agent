import asyncio
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

MAX_MATCHES = 50


class SearchFilesInput(BaseModel):
    pattern: str = Field(description="Search pattern (regex supported)")
    directory: str = Field(default=".", description="Directory to search in")
    file_glob: str | None = Field(default=None, description="File pattern filter, e.g. '*.ts' or '*.py'")


async def search_files(
    pattern: str,
    directory: str = ".",
    file_glob: str | None = None,
    project_root: Path | None = None,
) -> str:
    """
    Search for a pattern across files (grep-like).

    Tries rg (ripgrep) first, falls back to grep -rn.
    Truncates at 50 matches max.
    """
    try:
        resolved = Path(directory)
        if not resolved.is_absolute() and project_root:
            resolved = project_root / resolved

        if not resolved.is_dir():
            return f"✗ Directory not found: {directory}"

        if shutil.which("rg"):
            cmd = _build_rg_cmd(pattern, str(resolved), file_glob)
        else:
            cmd = _build_grep_cmd(pattern, str(resolved), file_glob)

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(resolved),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="replace")

        if not output.strip():
            return "No matches found"

        lines = output.strip().split("\n")
        if len(lines) > MAX_MATCHES:
            total = len(lines)
            lines = lines[:MAX_MATCHES]
            lines.append(f"\n[...truncated, showing {MAX_MATCHES} of {total} matches]")

        return "\n".join(lines)

    except asyncio.TimeoutError:
        return "✗ Search timed out after 30 seconds"
    except Exception as e:
        return f"✗ Error searching: {e}"


def _build_rg_cmd(pattern: str, directory: str, file_glob: str | None) -> str:
    """Build ripgrep command."""
    parts = ["rg", "--no-heading", "--line-number", "--color=never"]
    if file_glob:
        parts.extend(["-g", _shell_quote(file_glob)])
    parts.append(_shell_quote(pattern))
    parts.append(".")
    return " ".join(parts)


def _build_grep_cmd(pattern: str, directory: str, file_glob: str | None) -> str:
    """Build grep command."""
    parts = ["grep", "-rn", "--color=never"]
    parts.extend(["--exclude-dir=.git", "--exclude-dir=node_modules", "--exclude-dir=.shipyard"])
    if file_glob:
        parts.extend(["--include", _shell_quote(file_glob)])
    parts.append(_shell_quote(pattern))
    parts.append(".")
    return " ".join(parts)


def _shell_quote(s: str) -> str:
    """Simple shell quoting."""
    return "'" + s.replace("'", "'\\''") + "'"
