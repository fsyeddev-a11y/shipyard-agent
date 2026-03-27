# Spec 01: Whitespace Normalization

## Objective
Create `shipyard/edit_engine/normalize.py` — functions to detect a file's whitespace conventions and normalize LLM-produced content to match. LLMs frequently add/drop trailing spaces, change indentation style, or use different line endings. This module fixes that before edits are applied.

## Dependencies
- Phase 1 complete (project structure exists)

## File: `shipyard/edit_engine/normalize.py`

### Functions to Implement

```python
from dataclasses import dataclass


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
    - Count occurrences of \r\n vs bare \n
    - Majority wins
    - Default to \n if file is empty or has no line endings
    """


def normalize_content(new_content: str, file_style: FileStyle) -> str:
    """
    Normalize new_content to match the file's detected style.

    Steps:
    1. Normalize line endings: convert all \r\n or \n to the file's convention
    2. Normalize indentation: if the file uses tabs and new_content uses spaces
       (or vice versa), convert. Use indent_size for the conversion ratio.
    3. Strip trailing whitespace from each line (LLMs often add random trailing spaces)
    4. Ensure file ends with exactly one newline (no trailing blank lines, but
       always a final newline)

    Returns the normalized content string.
    """


def normalize_for_edit(new_content: str, original_content: str) -> str:
    """
    Convenience function: detect style from original_content, then normalize new_content.
    This is what the edit engine calls.
    """
    style = detect_style(original_content)
    return normalize_content(new_content, style)
```

### Implementation Notes

- Indentation detection should look at the **leading whitespace** of each line, ignoring blank lines
- For indent size detection: collect all leading space counts, find the GCD or most common factor of 2 or 4
- The normalization should be conservative — only convert if there's a clear mismatch. If `new_content` already matches the file style, return it unchanged (minus trailing whitespace cleanup)
- Trailing whitespace stripping applies to every line unconditionally — this is always safe
- The final newline rule: `content.rstrip('\n\r') + line_ending`

### Edge Cases
- Empty file: default to FileStyle(indent_char=" ", indent_size=4, line_ending="\n")
- File with mixed indentation: go with majority
- new_content that's a single line with no indentation: return as-is (just line ending normalization)
- Tab-indented file receiving space-indented content: convert spaces to tabs

## Acceptance Criteria
- [ ] `detect_style` correctly identifies tabs vs spaces
- [ ] `detect_style` correctly identifies indent size (2 or 4)
- [ ] `detect_style` correctly identifies \n vs \r\n
- [ ] `normalize_content` converts line endings
- [ ] `normalize_content` converts indentation style
- [ ] `normalize_content` strips trailing whitespace per line
- [ ] `normalize_content` ensures single trailing newline
- [ ] `normalize_for_edit` is the one-call convenience wrapper
- [ ] Empty/minimal inputs don't crash
