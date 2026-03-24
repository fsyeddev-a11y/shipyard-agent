import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

MAX_LINES = 200
TIMEOUT_SECONDS = 60


class RunCommandInput(BaseModel):
    command: str = Field(description="Shell command to execute")
    working_directory: str | None = Field(default=None, description="Working directory (defaults to project root)")


async def run_command(
    command: str,
    working_directory: str | None = None,
    project_root: Path | None = None,
) -> str:
    """
    Execute a shell command and return its output.

    Uses asyncio.create_subprocess_shell with 60s timeout.
    Truncates output at 200 lines (first 100 + last 100).
    """
    try:
        cwd = working_directory
        if cwd:
            resolved = Path(cwd)
            if not resolved.is_absolute() and project_root:
                resolved = project_root / resolved
            cwd = str(resolved)
        elif project_root:
            cwd = str(project_root)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)

        output = stdout.decode("utf-8", errors="replace")
        err_output = stderr.decode("utf-8", errors="replace")

        combined = output
        if err_output:
            combined += "\n" + err_output if combined else err_output

        combined = _truncate(combined)
        return f"Exit code: {proc.returncode}\n\n{combined}"

    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return f"✗ Command timed out after {TIMEOUT_SECONDS} seconds"
    except Exception as e:
        return f"✗ Error running command: {e}"


def _truncate(output: str) -> str:
    """Truncate output to MAX_LINES, keeping first 100 and last 100."""
    lines = output.split("\n")
    if len(lines) <= MAX_LINES:
        return output

    head = lines[:100]
    tail = lines[-100:]
    skipped = len(lines) - 200
    return "\n".join(head) + f"\n\n[...truncated {skipped} lines...]\n\n" + "\n".join(tail)
