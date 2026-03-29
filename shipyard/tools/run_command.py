import asyncio
import os
import signal
from pathlib import Path

from pydantic import BaseModel, Field

MAX_LINES = 200
TIMEOUT_SECONDS = 60
BACKGROUND_STARTUP_WAIT = 3  # seconds to wait for startup output

# Track background processes
_background_processes: dict[int, asyncio.subprocess.Process] = {}


class RunCommandInput(BaseModel):
    command: str = Field(description="Shell command to execute")
    working_directory: str | None = Field(default=None, description="Working directory (defaults to project root)")
    background: bool = Field(default=False, description="Run in background. Returns PID and initial output. Use for servers that run forever.")


class StopBackgroundInput(BaseModel):
    pid: int = Field(description="PID of the background process to stop")


async def run_command(
    command: str,
    working_directory: str | None = None,
    background: bool = False,
    project_root: Path | None = None,
) -> str:
    """
    Execute a shell command and return its output.

    If background=True: starts the process, waits 3 seconds for initial output
    (to catch startup errors), then returns the PID. The process keeps running.
    Use stop_background to kill it later.

    If background=False: runs with 60s timeout, returns full output.
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

        if background:
            return await _run_background(command, cwd)
        else:
            return await _run_foreground(command, cwd)

    except Exception as e:
        return f"✗ Error running command: {e}"


async def _run_foreground(command: str, cwd: str | None) -> str:
    """Run a command and wait for it to finish (with timeout)."""
    try:
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


async def _run_background(command: str, cwd: str | None) -> str:
    """Start a background process, wait briefly for startup output, return PID."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        preexec_fn=os.setsid,  # Create new process group so we can kill it later
    )

    pid = proc.pid
    _background_processes[pid] = proc

    # Wait a few seconds to capture startup output or crash
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=BACKGROUND_STARTUP_WAIT
        )
        # Process exited within startup wait — it crashed
        output = stdout.decode("utf-8", errors="replace")
        err_output = stderr.decode("utf-8", errors="replace")
        combined = output + ("\n" + err_output if err_output else "")
        del _background_processes[pid]
        return f"✗ Background process crashed immediately (exit code {proc.returncode}):\n\n{_truncate(combined)}"

    except asyncio.TimeoutError:
        # Process is still running — that's what we want for a server
        # Try to read whatever output is available
        initial_output = ""
        try:
            # Read available stdout without blocking
            stdout_data = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.5)
            initial_output = stdout_data.decode("utf-8", errors="replace")
        except (asyncio.TimeoutError, Exception):
            pass

        return (
            f"✓ Background process started (PID: {pid})\n"
            f"Command: {command}\n"
            f"Working directory: {cwd}\n"
            f"{('Initial output: ' + initial_output) if initial_output else 'No initial output captured.'}\n"
            f"Use stop_background with PID {pid} to stop it."
        )


async def stop_background(
    pid: int,
    project_root: Path | None = None,
) -> str:
    """Stop a background process by PID."""
    proc = _background_processes.get(pid)

    if proc:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            await asyncio.sleep(1)
            if proc.returncode is None:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            del _background_processes[pid]
            return f"✓ Stopped background process (PID: {pid})"
        except (ProcessLookupError, OSError):
            if pid in _background_processes:
                del _background_processes[pid]
            return f"✓ Process {pid} already exited"
    else:
        # Try killing by PID directly (process started in a previous session)
        try:
            os.kill(pid, signal.SIGTERM)
            return f"✓ Sent SIGTERM to PID {pid}"
        except ProcessLookupError:
            return f"✗ No process found with PID {pid}"
        except PermissionError:
            return f"✗ Permission denied killing PID {pid}"


def _truncate(output: str) -> str:
    """Truncate output to MAX_LINES, keeping first 100 and last 100."""
    lines = output.split("\n")
    if len(lines) <= MAX_LINES:
        return output

    head = lines[:100]
    tail = lines[-100:]
    skipped = len(lines) - 200
    return "\n".join(head) + f"\n\n[...truncated {skipped} lines...]\n\n" + "\n".join(tail)
