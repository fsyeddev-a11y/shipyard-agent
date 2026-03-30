"""
Multi-agent state schemas for Shipyard.

Defines state for supervisor, workers, and the shared orchestrator.
Used by the supervisor graph for task decomposition, worker dispatch,
and merge coordination.
"""

from typing import TypedDict, Annotated, Sequence, Optional
from dataclasses import dataclass, field
from enum import Enum
import time

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel


# --- Enums ---

class TaskMode(str, Enum):
    DIRECT = "direct"      # Single-agent, supervisor executes directly
    PARALLEL = "parallel"  # Multi-agent, workers in parallel


class WorkerPhase(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"


# --- Subtask / Decomposition ---

class Subtask(BaseModel):
    """A subtask assigned to a worker by the supervisor."""
    id: str
    instruction: str
    files_owned: list[str]       # Files this worker can edit
    files_readable: list[str]    # Files this worker can read (not edit)
    priority: int = 0            # Lower = higher priority


class DecompositionResult(BaseModel):
    """Output of the supervisor's decompose step."""
    mode: TaskMode
    subtasks: list[Subtask] = []
    shared_files: list[str] = []  # Files no worker owns; edits via request_shared_edit
    reasoning: str = ""


# --- Worker State ---

class PlannedEdit(BaseModel):
    """A single planned edit within a worker's plan."""
    file: str
    description: str
    order: int


class WorkerState(TypedDict):
    """LangGraph state for a worker subgraph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    subtask: dict          # Subtask as dict for serialization
    files_owned: list[str]
    files_readable: list[str]
    edit_plan: list[dict]  # List of PlannedEdit dicts
    edits_completed: int
    retry_count: int
    max_retries: int
    worker_id: str
    status: str            # WorkerPhase value


# --- Change Request (shared file edits) ---

class ChangeRequest(BaseModel):
    """A deferred edit to a shared file, requested by a worker."""
    worker_id: str
    file_path: str
    description: str
    old_content: str
    new_content: str


# --- Worker Result ---

class WorkerResult(BaseModel):
    """Result returned by a worker after completion or failure."""
    worker_id: str
    success: bool
    files_modified: list[str] = []
    diffs: list[str] = []
    error: Optional[str] = None
    change_requests: list[ChangeRequest] = []


# --- Supervisor State ---

class SupervisorState(TypedDict):
    """LangGraph state for the supervisor graph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    instruction: str
    decomposition: Optional[dict]         # DecompositionResult as dict
    subtasks: list[dict]                  # List of Subtask dicts
    worker_results: dict[str, dict]       # worker_id -> WorkerResult dict
    change_requests: list[dict]           # List of ChangeRequest dicts
    validation_result: Optional[dict]
    replan_count: int
    max_replans: int


# --- Shared Orchestrator State (in-memory, not LangGraph) ---

@dataclass
class WorkerStatus:
    """Real-time status of a worker, updated via heartbeat."""
    phase: WorkerPhase = WorkerPhase.PLANNING
    current_file: Optional[str] = None
    edits_completed: int = 0
    edits_planned: int = 0
    last_update: float = field(default_factory=time.time)


class OrchestratorState:
    """
    In-memory shared state between supervisor and workers.

    Safe with async Python (cooperative yielding, no race conditions
    since workers run via asyncio.gather in the same event loop).
    """

    def __init__(self):
        self.worker_status: dict[str, WorkerStatus] = {}
        self.change_requests: list[ChangeRequest] = []
        self.worker_results: dict[str, WorkerResult] = {}

    def register_worker(self, worker_id: str):
        self.worker_status[worker_id] = WorkerStatus()

    def update_heartbeat(
        self,
        worker_id: str,
        phase: WorkerPhase,
        current_file: Optional[str] = None,
        edits_completed: int = 0,
        edits_planned: int = 0,
    ):
        if worker_id not in self.worker_status:
            self.register_worker(worker_id)
        status = self.worker_status[worker_id]
        status.phase = phase
        status.current_file = current_file
        status.edits_completed = edits_completed
        status.edits_planned = edits_planned
        status.last_update = time.time()

    def add_change_request(self, request: ChangeRequest):
        self.change_requests.append(request)

    def set_worker_result(self, result: WorkerResult):
        self.worker_results[result.worker_id] = result

    def get_timed_out_workers(self, timeout_seconds: int = 120) -> list[str]:
        """Return worker_ids that haven't updated within timeout."""
        now = time.time()
        timed_out = []
        for wid, status in self.worker_status.items():
            if status.phase not in (WorkerPhase.COMPLETE, WorkerPhase.FAILED):
                if now - status.last_update > timeout_seconds:
                    timed_out.append(wid)
        return timed_out

    def all_workers_done(self) -> bool:
        return all(
            s.phase in (WorkerPhase.COMPLETE, WorkerPhase.FAILED)
            for s in self.worker_status.values()
        )
