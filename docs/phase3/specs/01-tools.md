# Spec 01: Tool Implementations

## Objective
Implement the 6 core tools the agent uses to interact with the codebase. Each tool is a standalone async function that returns structured output. These tools will be registered with LangGraph in spec 02.

## Dependencies
- Phase 2 complete (edit engine for edit_file/edit_file_multi)
- Phase 1 complete (config for project_root)

## Files to Implement

### `shipyard/tools/read_file.py`

```python
from pydantic import BaseModel, Field


class ReadFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to read (relative to project root)")
    start_line: int | None = Field(default=None, description="Starting line number (1-based). Omit to read from beginning.")
    end_line: int | None = Field(default=None, description="Ending line number (1-based, inclusive). Omit to read to end.")


async def read_file(file_path: str, start_line: int | None = None, end_line: int | None = None, project_root=None) -> str:
    """
    Read a file and return its contents with line numbers prepended.

    Output format (matches what LLMs expect):
      1 | first line of file
      2 | second line of file
      ...

    If start_line/end_line are provided, only return that range.
    Line numbers are 1-based.

    Errors:
    - File not found → return error message (don't raise)
    - Directory instead of file → return error message
    """
```

### `shipyard/tools/edit_file.py`

```python
from pydantic import BaseModel, Field


class EditFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to edit (relative to project root)")
    old_content: str = Field(description="The exact text to find and replace. Must match exactly once in the file.")
    new_content: str = Field(description="The replacement text")
    description: str = Field(default="", description="Brief description of the change (used in commit message)")


class EditFileMultiInput(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    edits: list[dict] = Field(description="List of {old_content, new_content} pairs to apply atomically")
    description: str = Field(default="", description="Brief description of the changes")


async def edit_file(file_path: str, old_content: str, new_content: str, description: str = "", project_root=None) -> str:
    """
    Make a surgical edit to a file using anchor-based replacement.

    Delegates to edit_engine.apply_edit(). Returns a human-readable
    summary string:
    - Success: "✓ Edited {file_path}: {diff_summary} (commit: {hash})"
    - Error: "✗ {error_type}: {error_detail}" + file_context if available
    """


async def edit_file_multi(file_path: str, edits: list[dict], description: str = "", project_root=None) -> str:
    """
    Apply multiple edits to a single file atomically.

    Delegates to edit_engine.apply_edit_multi(). Same return format as edit_file.
    """
```

### `shipyard/tools/create_file.py`

```python
from pydantic import BaseModel, Field


class CreateFileInput(BaseModel):
    file_path: str = Field(description="Path for the new file (relative to project root)")
    content: str = Field(description="Content to write to the file")


async def create_file(file_path: str, content: str, project_root=None) -> str:
    """
    Create a new file with the given content.

    - If file already exists → return error (don't overwrite)
    - Create parent directories if they don't exist
    - Git commit the new file
    - Return: "✓ Created {file_path} ({line_count} lines)"
    - Error: "✗ File already exists: {file_path}"
    """
```

### `shipyard/tools/list_files.py`

```python
from pydantic import BaseModel, Field


class ListFilesInput(BaseModel):
    directory: str = Field(default=".", description="Directory to list (relative to project root)")
    depth: int = Field(default=3, description="Maximum depth to traverse")


async def list_files(directory: str = ".", depth: int = 3, project_root=None) -> str:
    """
    List files in a directory tree.

    Output format (tree-like):
      src/
        components/
          Button.tsx
          Input.tsx
        utils/
          helpers.ts
      package.json
      tsconfig.json

    - Respects depth limit
    - Skips hidden directories (.git, .shipyard, node_modules)
    - Returns error message if directory doesn't exist
    """
```

### `shipyard/tools/search_files.py`

```python
from pydantic import BaseModel, Field


class SearchFilesInput(BaseModel):
    pattern: str = Field(description="Search pattern (regex supported)")
    directory: str = Field(default=".", description="Directory to search in")
    file_glob: str | None = Field(default=None, description="File pattern filter, e.g. '*.ts' or '*.py'")


async def search_files(pattern: str, directory: str = ".", file_glob: str | None = None, project_root=None) -> str:
    """
    Search for a pattern across files (grep-like).

    Uses subprocess to call `grep -rn` (or `rg` if available).

    Output format:
      src/auth.ts:15: export function validateEmail(email: string) {
      src/auth.ts:42: export function validatePassword(password: string) {
      src/types.ts:8: interface AuthConfig {

    - Truncate to 50 matches max (tell the agent if truncated)
    - Skip .git, node_modules, .shipyard directories
    - Return "No matches found" if nothing matches
    - Support file_glob filter: only search files matching the glob
    """
```

### `shipyard/tools/run_command.py`

```python
from pydantic import BaseModel, Field


class RunCommandInput(BaseModel):
    command: str = Field(description="Shell command to execute")
    working_directory: str | None = Field(default=None, description="Working directory (defaults to project root)")


async def run_command(command: str, working_directory: str | None = None, project_root=None) -> str:
    """
    Execute a shell command and return its output.

    - Runs via asyncio.create_subprocess_shell
    - Captures stdout and stderr
    - Timeout: 60 seconds (configurable later)
    - Output truncation: if stdout+stderr > 200 lines, truncate with
      "[...truncated {N} lines...]" marker. Return first 100 + last 100 lines.
    - Return format: "Exit code: {code}\n\n{output}"
    - On timeout: "✗ Command timed out after 60 seconds"
    """
```

## Implementation Notes

- All tools are async functions (even if they do sync I/O — we'll use `asyncio.to_thread` for blocking calls like file reads and subprocess)
- Each tool has a Pydantic `Input` model — these will be used by the tool registry (spec 02) for LangGraph registration
- The `project_root` parameter is injected at runtime by the tool registry, not passed by the LLM
- All tools return **strings** (not dicts/objects). The LLM reads tool output as text. Keep it clean and readable.
- Error handling: tools should NEVER raise exceptions to the LLM. Always return error strings.
- `edit_file` and `edit_file_multi` delegate entirely to the edit engine — they're thin wrappers that format the `EditResult` into a readable string
- `search_files` should try `rg` (ripgrep) first, fall back to `grep -rn`
- `list_files` skips: `.git/`, `.shipyard/`, `node_modules/`, `__pycache__/`, `.venv/`

## Acceptance Criteria
- [ ] All 6 tool modules importable from `shipyard.tools`
- [ ] Each tool has a Pydantic Input model
- [ ] `read_file` returns line-numbered content
- [ ] `edit_file` delegates to edit engine and returns formatted result
- [ ] `create_file` creates file, creates dirs, git commits, errors on existing
- [ ] `list_files` returns tree with depth limit
- [ ] `search_files` finds pattern matches with file:line format
- [ ] `run_command` executes command, truncates long output
- [ ] All tools return strings, never raise to the caller
