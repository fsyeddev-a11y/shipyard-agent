from pathlib import Path

from pydantic import BaseModel, Field


class WriteNoteInput(BaseModel):
    topic: str = Field(description="Note topic — used as filename (e.g., 'plan', 'progress', 'issues')")
    content: str = Field(description="Note content in markdown")


class ReadNotesInput(BaseModel):
    topic: str | None = Field(default=None, description="Specific topic to read. If omitted, lists all available notes with summaries.")


async def write_note(
    topic: str,
    content: str,
    project_root: Path,
) -> str:
    """
    Write a note to .shipyard/notes/{topic}.md.
    Creates the file if it doesn't exist, overwrites if it does.
    Used for: plans, progress tracking, issues, project context.
    """
    notes_dir = project_root / ".shipyard" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize topic for filename
    safe_topic = "".join(c if c.isalnum() or c in "-_" else "-" for c in topic).strip("-")
    if not safe_topic:
        return "✗ Invalid topic name"

    note_path = notes_dir / f"{safe_topic}.md"

    # Check note count limit
    existing_notes = list(notes_dir.glob("*.md"))
    if not note_path.exists() and len(existing_notes) >= 20:
        return f"✗ Note limit reached (20). Delete old notes before creating new ones."

    # Check content length
    if len(content) > 10000:
        return f"✗ Note content too long ({len(content)} chars). Maximum is 10,000 characters."

    note_path.write_text(content, encoding="utf-8")
    return f"✓ Note saved: .shipyard/notes/{safe_topic}.md ({len(content)} chars)"


async def read_notes(
    topic: str | None = None,
    project_root: Path | None = None,
) -> str:
    """
    Read notes from .shipyard/notes/.
    If topic is provided, read that specific note.
    If topic is None, list all notes with their first line as summary.
    """
    notes_dir = project_root / ".shipyard" / "notes"

    if not notes_dir.exists():
        return "No notes found. Use write_note to create one."

    if topic:
        safe_topic = "".join(c if c.isalnum() or c in "-_" else "-" for c in topic).strip("-")
        note_path = notes_dir / f"{safe_topic}.md"
        if not note_path.exists():
            # Try finding a close match
            available = [f.stem for f in notes_dir.glob("*.md")]
            if available:
                return f"✗ Note '{topic}' not found. Available notes: {', '.join(available)}"
            return f"✗ Note '{topic}' not found. No notes exist yet."
        return note_path.read_text(encoding="utf-8")

    # List all notes with summaries
    notes = sorted(notes_dir.glob("*.md"))
    if not notes:
        return "No notes found. Use write_note to create one."

    lines = [f"Available notes ({len(notes)}):"]
    for note in notes:
        content = note.read_text(encoding="utf-8")
        first_line = content.split("\n")[0].strip()[:80] if content.strip() else "(empty)"
        lines.append(f"  • {note.stem}: {first_line}")

    return "\n".join(lines)
