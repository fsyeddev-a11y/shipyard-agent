import json
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    """ISO timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


class BaseEvent(BaseModel):
    """Base class for all session events."""
    type: str
    ts: str = Field(default_factory=_now)
    session_id: str = ""


class SessionStartEvent(BaseEvent):
    type: str = "session_start"
    project_root: str = ""


class InstructionEvent(BaseEvent):
    type: str = "instruction"
    content: str = ""
    context_count: int = 0  # number of attached context items


class PlanEvent(BaseEvent):
    type: str = "plan"
    steps: list[str] = Field(default_factory=list)


class ToolCallEvent(BaseEvent):
    type: str = "tool_call"
    tool: str = ""
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResultEvent(BaseEvent):
    type: str = "tool_result"
    tool: str = ""
    output_summary: str = ""  # truncated for the log
    success: bool = True


class EditEvent(BaseEvent):
    type: str = "edit"
    file_path: str = ""
    diff_summary: str = ""  # "+N -M lines"
    commit_hash: str = ""
    validated: bool = True


class LLMCallEvent(BaseEvent):
    """Must include token counts — required for cost analysis."""
    type: str = "llm_call"
    model: str = ""
    tokens: dict[str, int] = Field(default_factory=lambda: {
        "input": 0, "output": 0, "cache_read": 0
    })
    cost: float = 0.0  # estimated cost in USD
    duration_ms: int = 0


class ContextEvictedEvent(BaseEvent):
    type: str = "context_evicted"
    content_summary: str = ""
    tier: str = ""  # which tier the content was evicted from
    tokens_freed: int = 0


class ContextInjectedEvent(BaseEvent):
    type: str = "context_injected"
    source: str = ""  # "human", "system", "attachment"
    label: str = ""
    tier: str = ""  # which tier it was added to
    token_count: int = 0


class TaskCompleteEvent(BaseEvent):
    type: str = "task_complete"
    summary: str = ""
    files_modified: list[str] = Field(default_factory=list)
    total_edits: int = 0


class WorkerDispatchedEvent(BaseEvent):
    type: str = "worker_dispatched"
    worker_id: str = ""
    subtask: str = ""
    files_owned: list[str] = Field(default_factory=list)


class WorkerCompletedEvent(BaseEvent):
    type: str = "worker_completed"
    worker_id: str = ""
    success: bool = True
    files_modified: list[str] = Field(default_factory=list)


class WorkerFailedEvent(BaseEvent):
    type: str = "worker_failed"
    worker_id: str = ""
    error: str = ""


class ErrorEvent(BaseEvent):
    type: str = "error"
    message: str = ""
    recoverable: bool = True


# Map type string to event class for deserialization
EVENT_TYPE_MAP: dict[str, type[BaseEvent]] = {
    "session_start": SessionStartEvent,
    "instruction": InstructionEvent,
    "plan": PlanEvent,
    "tool_call": ToolCallEvent,
    "tool_result": ToolResultEvent,
    "edit": EditEvent,
    "llm_call": LLMCallEvent,
    "context_evicted": ContextEvictedEvent,
    "context_injected": ContextInjectedEvent,
    "task_complete": TaskCompleteEvent,
    "worker_dispatched": WorkerDispatchedEvent,
    "worker_completed": WorkerCompletedEvent,
    "worker_failed": WorkerFailedEvent,
    "error": ErrorEvent,
}


def parse_event(line: str) -> BaseEvent:
    """Parse a JSONL line into the appropriate event object."""
    data = json.loads(line)
    event_type = data.get("type", "")
    cls = EVENT_TYPE_MAP.get(event_type, BaseEvent)
    return cls(**data)
