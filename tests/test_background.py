import pytest
import asyncio
from pathlib import Path
from shipyard.tools.run_command import run_command, stop_background, _background_processes


@pytest.mark.asyncio
async def test_background_server_starts(tmp_path):
    """Background process starts and returns PID."""
    result = await run_command(
        "python3.12 -m http.server 19876",
        background=True,
        project_root=tmp_path,
    )
    assert "Background process started" in result
    assert "PID:" in result

    # Extract PID and clean up
    import re
    pid_match = re.search(r"PID: (\d+)", result)
    assert pid_match
    pid = int(pid_match.group(1))
    await stop_background(pid)


@pytest.mark.asyncio
async def test_background_crash_detected(tmp_path):
    """Background process that crashes immediately is reported."""
    result = await run_command(
        "python3.12 -c 'raise Exception(\"crash\")'",
        background=True,
        project_root=tmp_path,
    )
    assert "crashed" in result.lower() or "exit code" in result.lower()


@pytest.mark.asyncio
async def test_stop_background_kills_process(tmp_path):
    """stop_background kills a running process."""
    result = await run_command(
        "python3.12 -m http.server 19877",
        background=True,
        project_root=tmp_path,
    )

    import re
    pid_match = re.search(r"PID: (\d+)", result)
    pid = int(pid_match.group(1))

    stop_result = await stop_background(pid)
    assert "Stopped" in stop_result or "exited" in stop_result


@pytest.mark.asyncio
async def test_stop_nonexistent_pid():
    """stop_background on a nonexistent PID returns error."""
    result = await stop_background(999999)
    assert "No process found" in result or "exited" in result


@pytest.mark.asyncio
async def test_foreground_still_works(tmp_path):
    """Regular (non-background) commands still work."""
    result = await run_command(
        "echo hello world",
        project_root=tmp_path,
    )
    assert "hello world" in result
    assert "Exit code: 0" in result


@pytest.mark.asyncio
async def test_foreground_timeout(tmp_path):
    """Foreground command that takes too long times out."""
    result = await run_command(
        "sleep 120",
        project_root=tmp_path,
    )
    assert "timed out" in result.lower()
