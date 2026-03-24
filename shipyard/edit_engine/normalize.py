from dataclasses import dataclass
from math import gcd
from functools import reduce


@dataclass
class FileStyle:
    """Detected whitespace conventions of a file."""
    indent_char: str        # "\t" or " "
    indent_size: int        # 2, 4, etc. (0 if tabs)
    line_ending: str        # "\n" or "\r\n"


def detect_style(content: str) -> FileStyle:
    """
    Analyze file content to detect indentation style and line endings.

    Indentation detection:
    - Count lines starting with tabs vs spaces
    - If spaces win, detect indent size by finding the most common
      leading-space count that is a multiple of 2 or 4
    - Default to 4 spaces if ambiguous or file has no indentation

    Line ending detection:
    - Count occurrences of \\r\\n vs bare \\n
    - Majority wins
    - Default to \\n if file is empty or has no line endings
    """
    if not content or not content.strip():
        return FileStyle(indent_char=" ", indent_size=4, line_ending="\n")

    # --- Line ending detection ---
    crlf_count = content.count("\r\n")
    # Bare \n = total \n minus those that are part of \r\n
    lf_count = content.count("\n") - crlf_count
    line_ending = "\r\n" if crlf_count > lf_count else "\n"

    # --- Indentation detection ---
    # Normalize to \n for line splitting
    lines = content.replace("\r\n", "\n").split("\n")

    tab_lines = 0
    space_lines = 0
    space_counts: list[int] = []

    for line in lines:
        if not line or not line[0] in (" ", "\t"):
            continue
        if line[0] == "\t":
            tab_lines += 1
        else:
            space_lines += 1
            leading = len(line) - len(line.lstrip(" "))
            if leading > 0:
                space_counts.append(leading)

    if tab_lines == 0 and space_lines == 0:
        return FileStyle(indent_char=" ", indent_size=4, line_ending=line_ending)

    if tab_lines > space_lines:
        return FileStyle(indent_char="\t", indent_size=0, line_ending=line_ending)

    # Spaces win — detect indent size
    indent_size = _detect_indent_size(space_counts)
    return FileStyle(indent_char=" ", indent_size=indent_size, line_ending=line_ending)


def _detect_indent_size(space_counts: list[int]) -> int:
    """Find the most likely indent size from a list of leading space counts."""
    if not space_counts:
        return 4

    # GCD of all space counts gives the base indent unit
    overall_gcd = reduce(gcd, space_counts)

    if overall_gcd >= 2:
        # Prefer 4 if it divides evenly, then 2
        if overall_gcd % 4 == 0:
            return 4
        if overall_gcd % 2 == 0:
            return overall_gcd if overall_gcd <= 4 else 2
        return overall_gcd

    # GCD is 1 — ambiguous, default to 4
    return 4


def normalize_content(new_content: str, file_style: FileStyle) -> str:
    """
    Normalize new_content to match the file's detected style.

    Steps:
    1. Normalize line endings: convert all \\r\\n or \\n to the file's convention
    2. Normalize indentation: if the file uses tabs and new_content uses spaces
       (or vice versa), convert. Use indent_size for the conversion ratio.
    3. Strip trailing whitespace from each line
    4. Ensure file ends with exactly one newline
    """
    if not new_content:
        return file_style.line_ending

    # Step 1: Normalize line endings to \n for processing
    text = new_content.replace("\r\n", "\n")
    lines = text.split("\n")

    # Step 2: Normalize indentation
    lines = _normalize_indentation(lines, file_style)

    # Step 3: Strip trailing whitespace from each line
    lines = [line.rstrip() for line in lines]

    # Step 4: Rejoin with file's line ending and ensure single trailing newline
    result = file_style.line_ending.join(lines)
    result = result.rstrip("\n\r") + file_style.line_ending
    return result


def _normalize_indentation(lines: list[str], file_style: FileStyle) -> list[str]:
    """Convert indentation in lines to match file_style."""
    # Detect what the new content uses
    has_tab_indent = any(line.startswith("\t") for line in lines if line.strip())
    has_space_indent = any(
        line.startswith(" ") and not line.startswith(" " * 1 + "\t")
        for line in lines if line.strip()
    )

    if file_style.indent_char == "\t" and has_space_indent and not has_tab_indent:
        # Convert spaces to tabs
        indent_size = file_style.indent_size if file_style.indent_size > 0 else 4
        return [_spaces_to_tabs(line, indent_size) for line in lines]
    elif file_style.indent_char == " " and has_tab_indent and not has_space_indent:
        # Convert tabs to spaces
        size = file_style.indent_size if file_style.indent_size > 0 else 4
        return [_tabs_to_spaces(line, size) for line in lines]

    return lines


def _spaces_to_tabs(line: str, indent_size: int) -> str:
    """Convert leading spaces to tabs."""
    if not line or not line.startswith(" "):
        return line
    leading = len(line) - len(line.lstrip(" "))
    tabs = leading // indent_size
    remainder = leading % indent_size
    return "\t" * tabs + " " * remainder + line.lstrip(" ")


def _tabs_to_spaces(line: str, indent_size: int) -> str:
    """Convert leading tabs to spaces."""
    if not line or not line.startswith("\t"):
        return line
    leading = len(line) - len(line.lstrip("\t"))
    return " " * (leading * indent_size) + line.lstrip("\t")


def normalize_for_edit(new_content: str, original_content: str) -> str:
    """
    Convenience function: detect style from original_content, then normalize new_content.
    This is what the edit engine calls.
    """
    style = detect_style(original_content)
    return normalize_content(new_content, style)
