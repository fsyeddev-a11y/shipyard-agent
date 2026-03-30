"""
Worker agent — a LangGraph subgraph that executes a single subtask.

Each worker:
1. Receives a subtask with file ownership assignments
2. Plans edits for its owned files
3. Executes edits via the tool suite (with ownership enforcement)
4. Validates results
5. Reports success/failure to shared orchestrator state

Workers can only edit files they own. For shared files, they use
request_shared_edit to queue deferred changes for the merge agent.
"""

import uuid
from typing import Annotated, Sequence

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

from shipyard.agent.llm import get_llm
from shipyard.agent.state import (
    WorkerState,
    WorkerPhase,
    WorkerResult,
    ChangeRequest,
    OrchestratorState,
)
from shipyard.tools.registry import ToolRegistry
from shipyard.config import ShipyardConfig


# --- Worker Constants ---

WORKER_MAX_MESSAGES = 60       # Hard limit per worker (~30 LLM turns)
WORKER_MAX_RETRIES = 3         # Max retries per edit target


WORKER_SYSTEM_PROMPT = """You are a Shipyard worker agent. You have been assigned a specific subtask with specific files to edit.

## Your Assignment
- You can ONLY edit files listed in your files_owned.
- You can READ any file in files_readable (and files_owned).
- For files you don't own, use request_shared_edit to queue changes for the merge agent.

## Workflow
1. Read your assigned files to understand the current state
2. Plan your edits (what changes, in what order)
3. Execute edits one at a time, verifying each succeeds before moving to the next
4. If an edit fails 3 times, report it and move on

## Rules
- ALWAYS read a file before editing it
- Use exact old_content matching — include enough context to be unambiguous
- Do NOT include line numbers from read_file output in old_content/new_content
- Be surgical — only change what's needed for your subtask
- If you need to modify a file you don't own, use request_shared_edit

Project root: {project_root}

## Your Subtask
{subtask_instruction}

## Files You Own (can read + write)
{files_owned}

## Files You Can Read (read-only)
{files_readable}
"""


def create_worker_graph(
    config: ShipyardConfig,
    orchestrator_state: OrchestratorState,
    worker_id: str,
    files_owned: list[str],
    files_readable: list[str] | None = None,
):
    """
    Create a worker LangGraph subgraph.

    The worker uses a ReAct loop (same pattern as the single-agent supervisor)
    but with file ownership enforcement via ToolRegistry.

    Args:
        config: ShipyardConfig
        orchestrator_state: Shared state for heartbeat + change requests
        worker_id: Unique identifier for this worker
        files_owned: Files this worker can edit
        files_readable: Additional files this worker can read

    Returns:
        Compiled LangGraph StateGraph
    """
    llm = get_llm(config)

    # Create tool registry with ownership enforcement
    registry = ToolRegistry(
        project_root=config.project_root,
        files_owned=files_owned,
    )
    tools = registry.get_tools()

    # Add request_shared_edit tool with orchestrator state injected
    from shipyard.tools.request_shared_edit import request_shared_edit, RequestSharedEditInput
    from langchain_core.tools import StructuredTool
    from functools import wraps

    @wraps(request_shared_edit)
    async def bound_shared_edit(**kwargs):
        kwargs["project_root"] = config.project_root
        kwargs["_orchestrator_state"] = orchestrator_state
        kwargs["_worker_id"] = worker_id
        return await request_shared_edit(**kwargs)

    shared_edit_tool = StructuredTool.from_function(
        coroutine=bound_shared_edit,
        name="request_shared_edit",
        description=(
            "Request an edit to a shared file you don't own. The edit will be "
            "applied by the merge agent after all workers complete. Provide "
            "file_path, description, old_content, and new_content."
        ),
        args_schema=RequestSharedEditInput,
    )
    tools.append(shared_edit_tool)

    model = llm.bind_tools(tools)

    # --- Worker nodes ---

    async def worker_agent_node(state: WorkerState) -> dict:
        """LLM reasoning node for the worker."""
        # Update heartbeat
        orchestrator_state.update_heartbeat(
            worker_id=worker_id,
            phase=WorkerPhase.EXECUTING,
            edits_completed=state.get("edits_completed", 0),
        )

        messages = state["messages"]
        response = await model.ainvoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    def should_continue(state: WorkerState) -> str:
        """Route to tools or end. Respects message limit."""
        messages = state["messages"]

        # Hard gate
        if len(messages) > WORKER_MAX_MESSAGES:
            return "end"

        last_message = messages[-1]
        if not (hasattr(last_message, "tool_calls") and last_message.tool_calls):
            return "end"

        return "tools"

    # --- Build graph ---
    graph = StateGraph(WorkerState)
    graph.add_node("agent", worker_agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile()


async def run_worker(
    subtask_instruction: str,
    config: ShipyardConfig,
    orchestrator_state: OrchestratorState,
    worker_id: str,
    files_owned: list[str],
    files_readable: list[str] | None = None,
) -> WorkerResult:
    """
    Run a single worker on a subtask.

    Creates the worker graph, executes it, and returns a WorkerResult.
    Updates the orchestrator state throughout execution.

    Args:
        subtask_instruction: What this worker should do
        config: ShipyardConfig
        orchestrator_state: Shared orchestrator state
        worker_id: Unique ID for this worker
        files_owned: Files this worker can edit
        files_readable: Additional read-only files

    Returns:
        WorkerResult with success status, files modified, and any errors
    """
    files_readable = files_readable or []

    # Register worker in orchestrator
    orchestrator_state.register_worker(worker_id)
    orchestrator_state.update_heartbeat(worker_id, WorkerPhase.PLANNING)

    graph = create_worker_graph(
        config=config,
        orchestrator_state=orchestrator_state,
        worker_id=worker_id,
        files_owned=files_owned,
        files_readable=files_readable,
    )

    # Build initial messages
    system_msg = SystemMessage(content=WORKER_SYSTEM_PROMPT.format(
        project_root=str(config.project_root),
        subtask_instruction=subtask_instruction,
        files_owned="\n".join(f"- {f}" for f in files_owned) or "(none)",
        files_readable="\n".join(f"- {f}" for f in files_readable) or "(none)",
    ))
    human_msg = HumanMessage(content=subtask_instruction)

    initial_state: WorkerState = {
        "messages": [system_msg, human_msg],
        "subtask": {"instruction": subtask_instruction},
        "files_owned": files_owned,
        "files_readable": files_readable,
        "edit_plan": [],
        "edits_completed": 0,
        "retry_count": 0,
        "max_retries": WORKER_MAX_RETRIES,
        "worker_id": worker_id,
        "status": WorkerPhase.PLANNING.value,
    }

    run_config = {
        "recursion_limit": WORKER_MAX_MESSAGES * 2,
        "metadata": {
            "worker_id": worker_id,
            "subtask": subtask_instruction[:200],
        },
        "tags": ["shipyard", "worker", worker_id],
    }

    # Execute the worker graph
    files_modified = []
    diffs = []
    error = None

    try:
        # Collect final state
        final_state = await graph.ainvoke(initial_state, config=run_config)

        # Scan messages for successful edits to track files_modified
        for msg in final_state.get("messages", []):
            content = str(getattr(msg, "content", ""))
            tool_name = getattr(msg, "name", "")
            if tool_name in ("edit_file", "edit_file_multi", "create_file") and content.startswith("\u2713"):
                # Extract file path from success message
                # Format: "✓ Edited <path>" or "✓ Created <path>"
                parts = content.split(" ", 2)
                if len(parts) >= 2:
                    # Try to extract path
                    for word in parts[1:]:
                        clean = word.strip().rstrip(":")
                        if "/" in clean or "." in clean:
                            files_modified.append(clean)
                            break

        orchestrator_state.update_heartbeat(worker_id, WorkerPhase.COMPLETE)

    except Exception as e:
        error = str(e)
        orchestrator_state.update_heartbeat(worker_id, WorkerPhase.FAILED)

    # Collect change requests this worker made
    worker_change_requests = [
        cr for cr in orchestrator_state.change_requests
        if cr.worker_id == worker_id
    ]

    result = WorkerResult(
        worker_id=worker_id,
        success=error is None,
        files_modified=list(set(files_modified)),
        diffs=diffs,
        error=error,
        change_requests=worker_change_requests,
    )

    orchestrator_state.set_worker_result(result)
    return result
