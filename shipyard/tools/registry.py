from functools import partial
from pathlib import Path

from langchain_core.tools import StructuredTool

from shipyard.tools.read_file import read_file, ReadFileInput
from shipyard.tools.edit_file import edit_file, edit_file_multi, EditFileInput, EditFileMultiInput
from shipyard.tools.create_file import create_file, CreateFileInput
from shipyard.tools.list_files import list_files, ListFilesInput
from shipyard.tools.search_files import search_files, SearchFilesInput
from shipyard.tools.run_command import run_command, RunCommandInput


class ToolRegistry:
    """
    Manages tool registration and provides LangGraph-compatible tool definitions.

    Usage:
        registry = ToolRegistry(project_root=Path("/path/to/project"))
        tools = registry.get_tools()
        # Bind to LLM: model.bind_tools(tools)
    """

    def __init__(
        self,
        project_root: Path,
        files_owned: list[str] | None = None,
    ):
        self.project_root = project_root
        self.files_owned = files_owned

    def get_tools(self) -> list[StructuredTool]:
        """
        Return list of LangGraph-compatible tools.

        Each tool has project_root pre-injected via functools.partial.
        If files_owned is set, edit_file and create_file are wrapped
        with ownership checks.
        """
        tools = [
            self._make_tool(
                "read_file",
                "Read a file's contents with line numbers. Supports optional line range (start_line, end_line).",
                read_file,
                ReadFileInput,
            ),
            self._make_tool(
                "edit_file",
                "Make a surgical edit to a file. Provide the exact text to find (old_content) and its replacement (new_content). The old_content must match exactly once in the file.",
                self._wrap_edit(edit_file),
                EditFileInput,
            ),
            self._make_tool(
                "edit_file_multi",
                "Apply multiple edits to a single file atomically. All edits succeed or none are applied. Provide a list of {old_content, new_content} pairs.",
                self._wrap_edit(edit_file_multi),
                EditFileMultiInput,
            ),
            self._make_tool(
                "create_file",
                "Create a new file. Fails if the file already exists. Parent directories are created automatically.",
                self._wrap_edit(create_file),
                CreateFileInput,
            ),
            self._make_tool(
                "list_files",
                "List files and directories in a tree format. Configurable depth. Skips hidden and generated directories.",
                list_files,
                ListFilesInput,
            ),
            self._make_tool(
                "search_files",
                "Search for a pattern across files (grep/ripgrep). Returns matching lines with file paths and line numbers. Supports regex and file glob filters.",
                search_files,
                SearchFilesInput,
            ),
            self._make_tool(
                "run_command",
                "Execute a shell command and return stdout/stderr. Output is truncated if longer than 200 lines.",
                run_command,
                RunCommandInput,
            ),
        ]
        return tools

    def _make_tool(self, name: str, description: str, func, input_model) -> StructuredTool:
        """Create a StructuredTool with project_root pre-injected."""
        bound_func = partial(func, project_root=self.project_root)

        return StructuredTool.from_function(
            coroutine=bound_func,
            name=name,
            description=description,
            args_schema=input_model,
        )

    def _wrap_edit(self, func):
        """Wrap an edit/create function with ownership check if files_owned is set."""
        if self.files_owned is None:
            return func

        async def wrapped(file_path: str, *args, **kwargs):
            if file_path not in self.files_owned:
                return (
                    f"\u2717 Ownership error: {file_path} is not owned by this worker. "
                    "Use request_shared_edit instead."
                )
            return await func(file_path, *args, **kwargs)

        wrapped.__name__ = func.__name__
        wrapped.__doc__ = func.__doc__
        return wrapped
