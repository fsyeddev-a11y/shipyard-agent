from pathlib import Path

from pydantic import BaseModel, Field


class ReadFileInput(BaseModel):
    file_path: str = Field(description="Path to the file to read (relative to project root)")
    start_line: int | None = Field(default=None, description="Starting line number (1-based). Omit to read from beginning.")
    end_line: int | None = Field(default=None, description="Ending line number (1-based, inclusive). Omit to read to end.")


async def read_file(
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    project_root: Path | None = None,
) -> str:
    """
    Read a file and return its contents with line numbers prepended.

    Output format:
      1 | first line of file
      2 | second line of file

    If start_line/end_line are provided, only return that range.
    Line numbers are 1-based.
    """
    try:
        resolved = Path(file_path)
        if not resolved.is_absolute() and project_root:
            resolved = project_root / resolved

        if resolved.is_dir():
            return f"✗ {file_path} is a directory, not a file"

        content = resolved.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Apply line range
        if start_line is not None or end_line is not None:
            s = (start_line or 1) - 1  # convert to 0-based
            e = end_line or len(lines)
            selected = lines[s:e]
            offset = s + 1
        else:
            selected = lines
            offset = 1

        # Format with line numbers
        width = len(str(offset + len(selected) - 1)) if selected else 1
        numbered = [f"{i + offset:>{width}} | {line}" for i, line in enumerate(selected)]
        return "\n".join(numbered)

    except FileNotFoundError:
        return f"✗ File not found: {file_path}"
    except Exception as e:
        return f"✗ Error reading {file_path}: {e}"
