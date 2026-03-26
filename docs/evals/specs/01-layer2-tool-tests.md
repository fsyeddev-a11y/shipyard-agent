# Spec 01: Layer 2 — Tool Integration Tests

## Objective
Create `tests/test_tools.py` implementing evals E-2.1 through E-2.7 from EVALS.md. Each test sets up a known filesystem state, calls a tool directly (no LLM), and asserts the output.

## Dependencies
- Phase 3 tools must be complete (they are)
- Edit engine + git helpers from Phases 1-2

## File: `tests/test_tools.py`

### Fixtures

```python
import pytest
import asyncio
from pathlib import Path
from shipyard.edit_engine.git import git_init_if_needed, git_commit


@pytest.fixture
def project(tmp_path):
    """Create a temporary git repo."""
    git_init_if_needed(tmp_path)
    return tmp_path


def _write(project: Path, name: str, content: str) -> str:
    """Helper: write a file, git commit it, return path."""
    f = project / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content)
    git_commit(name, project, f"setup: {name}")
    return name
```

### E-2.1: read_file

```python
@pytest.mark.asyncio
async def test_read_file_full(project):
    """E-2.1: Read a 50-line file, output has all lines with line numbers."""
    content = "\n".join(f"line {i}" for i in range(1, 51)) + "\n"
    _write(project, "test.ts", content)

    from shipyard.tools.read_file import read_file
    result = await read_file("test.ts", project_root=project)

    # Should have line numbers prepended
    assert "1 |" in result or "1\t" in result
    assert "50 |" in result or "50\t" in result
    # Should contain all lines
    assert "line 1" in result
    assert "line 50" in result


@pytest.mark.asyncio
async def test_read_file_line_range(project):
    """E-2.1: Read lines 50-75 of a 200-line file."""
    content = "\n".join(f"line {i}" for i in range(1, 201)) + "\n"
    _write(project, "test.ts", content)

    from shipyard.tools.read_file import read_file
    result = await read_file("test.ts", start_line=50, end_line=75, project_root=project)

    assert "line 50" in result
    assert "line 75" in result
    assert "line 49" not in result
    assert "line 76" not in result
```

### E-2.2: edit_file

```python
@pytest.mark.asyncio
async def test_edit_file_success(project):
    """E-2.2: Edit a function, verify file changed and git committed."""
    content = 'function greet(name: string) { return "hello " + name; }\n'
    _write(project, "test.ts", content)

    from shipyard.tools.edit_file import edit_file
    result = await edit_file(
        "test.ts",
        old_content='return "hello " + name',
        new_content='return `Hello, ${name}!`',
        description="update greeting",
        project_root=project,
    )

    assert "✓" in result  # success marker
    # Verify file on disk
    new_content = (project / "test.ts").read_text()
    assert "Hello, ${name}!" in new_content
    assert '"hello " + name' not in new_content


@pytest.mark.asyncio
async def test_edit_file_ambiguous(project):
    """E-2.2: Ambiguous anchor returns error."""
    content = "duplicate body\nother\nduplicate body\n"
    _write(project, "test.ts", content)

    from shipyard.tools.edit_file import edit_file
    result = await edit_file(
        "test.ts",
        old_content="duplicate body",
        new_content="unique body",
        project_root=project,
    )

    assert "ambiguous" in result.lower() or "✗" in result
```

### E-2.3: search_files

```python
@pytest.mark.asyncio
async def test_search_files_multiple_matches(project):
    """E-2.3: Search across 5 files, 3 contain the pattern."""
    _write(project, "a.ts", "export function createUser() {}\n")
    _write(project, "b.ts", "import { createUser } from './a';\n")
    _write(project, "c.ts", "const user = createUser('test');\n")
    _write(project, "d.ts", "export function deleteUser() {}\n")
    _write(project, "e.ts", "export function updateUser() {}\n")

    from shipyard.tools.search_files import search_files
    result = await search_files("createUser", ".", project_root=project)

    # Should find matches in a.ts, b.ts, c.ts
    assert "a.ts" in result
    assert "b.ts" in result
    assert "c.ts" in result
    # d.ts and e.ts don't contain createUser
    lines = result.strip().split("\n")
    matching_files = set()
    for line in lines:
        if "createUser" in line:
            matching_files.add(line.split(":")[0].split("/")[-1])
    assert len(matching_files) == 3
```

### E-2.4: run_command

```python
@pytest.mark.asyncio
async def test_run_command_success(project):
    """E-2.4: Echo command returns stdout."""
    from shipyard.tools.run_command import run_command
    result = await run_command("echo hello world", project_root=project)

    assert "hello world" in result
    assert "Exit code: 0" in result


@pytest.mark.asyncio
async def test_run_command_stderr(project):
    """E-2.4: Failed command returns stderr."""
    from shipyard.tools.run_command import run_command
    result = await run_command("cat nonexistent_file_xyz", project_root=project)

    # Should capture the error (non-zero exit or stderr content)
    assert "No such file" in result or "Exit code:" in result
```

### E-2.5: create_file

```python
@pytest.mark.asyncio
async def test_create_file_success(project):
    """E-2.5: Create file in nested directory."""
    from shipyard.tools.create_file import create_file
    result = await create_file(
        "src/utils.ts",
        "export function add(a, b) { return a + b; }",
        project_root=project,
    )

    assert "✓" in result or "Created" in result
    assert (project / "src" / "utils.ts").exists()
    assert "add" in (project / "src" / "utils.ts").read_text()


@pytest.mark.asyncio
async def test_create_file_already_exists(project):
    """E-2.5: Creating existing file returns error."""
    _write(project, "src/utils.ts", "existing content")

    from shipyard.tools.create_file import create_file
    result = await create_file(
        "src/utils.ts",
        "new content",
        project_root=project,
    )

    assert "exists" in result.lower() or "✗" in result
    # Original content preserved
    assert (project / "src" / "utils.ts").read_text() == "existing content"
```

### E-2.6: request_shared_edit (skip for now)

E-2.6 tests `request_shared_edit` which requires orchestrator state from Phase 5 (multi-agent). **Skip this test** — mark it with `@pytest.mark.skip(reason="Requires Phase 5 multi-agent")`.

### E-2.7: edit_file with ownership enforcement

```python
@pytest.mark.asyncio
async def test_edit_file_ownership_enforced(project):
    """E-2.7: Edit on non-owned file returns error."""
    _write(project, "auth.ts", "export function login() {}\n")
    _write(project, "dashboard.ts", "export function render() {}\n")

    from shipyard.tools.registry import ToolRegistry
    registry = ToolRegistry(project_root=project, files_owned=["auth.ts"])
    tools = registry.get_tools()

    # Find the edit_file tool
    edit_tool = next(t for t in tools if t.name == "edit_file")

    # Try editing a non-owned file
    result = await edit_tool.ainvoke({
        "file_path": "dashboard.ts",
        "old_content": "export function render() {}",
        "new_content": "export function render() { console.log('hi'); }",
    })

    assert "not owned" in str(result).lower() or "ownership" in str(result).lower()
```

## Implementation Notes

- All tests use `tmp_path` via the `project` fixture — isolated git repos
- Files are committed after creation so the edit engine's git operations work
- All tool calls are async — use `@pytest.mark.asyncio`
- Tests import tools directly, no LLM involved
- E-2.6 is skipped (requires multi-agent infrastructure)
- The ownership test (E-2.7) uses `ToolRegistry` with `files_owned` to test enforcement

## Acceptance Criteria
- [ ] `pytest tests/test_tools.py -v` — all tests pass (E-2.6 skipped)
- [ ] Tests cover: read_file (full + range), edit_file (success + ambiguous), search_files, run_command (success + error), create_file (success + exists), ownership enforcement
- [ ] No LLM calls — these are pure integration tests
- [ ] Each test is self-contained with its own temp git repo
