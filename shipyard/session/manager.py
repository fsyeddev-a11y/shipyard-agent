import uuid
from pathlib import Path
from shipyard.session.events import (
    BaseEvent, SessionStartEvent,
    parse_event,
)
from shipyard.config import ShipyardConfig


class SessionManager:
    """
    Manages session lifecycle and JSONL event logging.

    Usage:
        sm = SessionManager(config)
        session_id = sm.start_session()
        sm.log_event(ToolCallEvent(tool="read_file", args={"file_path": "x.ts"}))
        sm.log_event(TaskCompleteEvent(summary="Done"))
    """

    def __init__(self, config: ShipyardConfig):
        self.config = config
        self.sessions_path = config.sessions_path
        self.sessions_path.mkdir(parents=True, exist_ok=True)
        self.current_session_id: str | None = None
        self._log_file = None

    def start_session(self, session_id: str | None = None) -> str:
        """
        Start a new session or resume an existing one.

        Args:
            session_id: If provided, resume this session. Otherwise create new.

        Returns:
            The session ID
        """
        if session_id:
            self.current_session_id = session_id
        else:
            self.current_session_id = str(uuid.uuid4())

        if not session_id:
            # New session — write session_start event
            self.log_event(SessionStartEvent(
                project_root=str(self.config.project_root)
            ))

        return self.current_session_id

    def log_event(self, event: BaseEvent) -> None:
        """
        Append an event to the current session's JSONL log.

        The event's session_id is set to the current session.
        Each event is one JSON line.
        """
        if not self.current_session_id:
            return  # silently skip if no session

        event.session_id = self.current_session_id
        log_path = self._session_log_path(self.current_session_id)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def list_sessions(self) -> list[dict]:
        """
        List all sessions with basic metadata.

        Returns list of dicts:
        [
            {"session_id": "...", "created_at": "...", "instruction_count": N, "status": "..."},
            ...
        ]

        Status is determined by:
        - "completed" if last instruction has a matching task_complete
        - "interrupted" if last instruction has no task_complete
        - "active" if session is currently in progress
        """
        sessions = []
        for log_file in sorted(self.sessions_path.glob("*.jsonl"), reverse=True):
            session_id = log_file.stem
            events = self._read_events(session_id)
            if not events:
                continue

            created_at = events[0].ts if events else ""
            instruction_count = sum(1 for e in events if e.type == "instruction")
            status = self._determine_status(events, session_id)

            sessions.append({
                "session_id": session_id,
                "created_at": created_at,
                "instruction_count": instruction_count,
                "status": status,
            })
        return sessions

    def get_session_events(self, session_id: str) -> list[BaseEvent]:
        """Read all events for a session."""
        return self._read_events(session_id)

    def export_session(self, session_id: str) -> str:
        """
        Export a session as readable markdown.

        Format:
        # Session {session_id}
        Started: {timestamp}

        ## Instruction 1
        > {instruction text}

        ### Tool Calls
        - read_file(file_path="...") -> success
        - edit_file(file_path="...") -> +3 -1 lines

        ### Result
        {task_complete summary}

        ## Token Usage
        Total input: N, output: M, estimated cost: $X.XX
        """
        events = self._read_events(session_id)
        if not events:
            return f"Session {session_id} not found."

        lines = [f"# Session {session_id}", f"Started: {events[0].ts}", ""]

        instruction_num = 0
        for event in events:
            if event.type == "instruction":
                instruction_num += 1
                lines.append(f"## Instruction {instruction_num}")
                lines.append(f"> {event.content}")
                lines.append("")
            elif event.type == "tool_call":
                lines.append(f"- **{event.tool}**({', '.join(f'{k}={repr(v)[:40]}' for k, v in event.args.items())})")
            elif event.type == "edit":
                lines.append(f"  - Edit: {event.file_path} {event.diff_summary} (commit: {event.commit_hash})")
            elif event.type == "llm_call":
                lines.append(f"  - LLM: {event.model} in={event.tokens.get('input', 0)} out={event.tokens.get('output', 0)} cost=${event.cost:.4f}")
            elif event.type == "task_complete":
                lines.append(f"\n**Result:** {event.summary}")
                lines.append(f"Files modified: {', '.join(event.files_modified)}")
                lines.append("")
            elif event.type == "error":
                lines.append(f"  - Error: {event.message}")

        # Token summary
        llm_events = [e for e in events if e.type == "llm_call"]
        if llm_events:
            total_in = sum(e.tokens.get("input", 0) for e in llm_events)
            total_out = sum(e.tokens.get("output", 0) for e in llm_events)
            total_cost = sum(e.cost for e in llm_events)
            lines.append(f"\n## Token Usage")
            lines.append(f"Total input: {total_in:,}, output: {total_out:,}, estimated cost: ${total_cost:.4f}")

        return "\n".join(lines)

    def _session_log_path(self, session_id: str) -> Path:
        return self.sessions_path / f"{session_id}.jsonl"

    def _read_events(self, session_id: str) -> list[BaseEvent]:
        log_path = self._session_log_path(session_id)
        if not log_path.exists():
            return []
        events = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(parse_event(line))
                    except Exception:
                        pass  # skip malformed lines
        return events

    def _determine_status(self, events: list[BaseEvent], session_id: str) -> str:
        if session_id == self.current_session_id:
            return "active"
        # Find last instruction and check if it has a matching task_complete
        last_instruction_idx = None
        for i, e in enumerate(events):
            if e.type == "instruction":
                last_instruction_idx = i
        if last_instruction_idx is None:
            return "completed"
        has_completion = any(
            e.type == "task_complete" for e in events[last_instruction_idx:]
        )
        return "completed" if has_completion else "interrupted"
