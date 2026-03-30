from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

import asyncio
import json
import uuid

from shipyard.agent.llm import get_llm
from shipyard.agent.state import (
    OrchestratorState,
    Subtask,
    DecompositionResult,
    TaskMode,
    WorkerResult,
    WorkerPhase,
)
from shipyard.tools.registry import ToolRegistry
from shipyard.config import ShipyardConfig
from shipyard.session.manager import SessionManager
from shipyard.session.events import InstructionEvent, TaskCompleteEvent
from shipyard.context.manager import ContextManager
from shipyard.middleware.hooks import AgentMiddleware
from shipyard.tracing import is_tracing_enabled, get_trace_url


# --- Circuit Breaker Config ---

HARD_MESSAGE_LIMIT = 100       # Absolute max messages (~50 LLM turns). Never exceeded.
SOFT_UNPRODUCTIVE_LIMIT = 5    # Stop after N consecutive unproductive turns (failed edits, retries)

# Tools that count as "productive" — they change something on disk
PRODUCTIVE_TOOLS = {"edit_file", "edit_file_multi", "create_file", "move_file", "delete_file", "write_note"}


# --- State ---

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# --- System Prompt ---

SYSTEM_PROMPT = """You are Shipyard, an autonomous coding agent. You make surgical, targeted edits to codebases.

## Planning (ALWAYS DO THIS FIRST)
1. Before ANY work: run list_files (depth=2) AND read_notes to check for existing plans or progress from prior work. If progress.md exists, resume from where the last session left off — do NOT restart from scratch.
2. For instructions touching 2+ files: output a plan listing EVERY file you will create or edit with its FULL path from project root. Resolve paths against the actual structure on disk.
3. CRITICAL: When creating files, resolve paths relative to what ALREADY EXISTS on disk. If you see directories like packages/api/ or src/components/, place new files inside those existing directories — never create duplicates at the root. The project structure you observe in list_files is the source of truth.
4. In the plan, for each file state: the full path, whether it's create or edit, and what changes you'll make.
5. You have a limited message budget (~12 turns). Plan efficiently — don't explore aimlessly.

## PRD-Driven Workflow (when given a PRD or large feature spec)
6. When given a PRD or large feature description, do NOT jump straight into coding. First:
   a. Read the full PRD and identify all deliverables.
   b. Break the work into ordered specs (logical units of work). Each spec should be independently testable.
   c. Write the plan to .shipyard/notes/plan.md using write_note. Include: spec name, files involved (full paths), dependencies between specs, and verification steps.
   d. Implement specs one at a time.
7. Each spec should follow vertical development: create → verify → fix → next file.

## Progress Checkpoints (MANDATORY)
8. Use append_note (not write_note) for progress — it adds timestamped entries instead of overwriting.
9. At the START of every spec: append_note to "progress" with what you are about to do.
10. At the END of every completed spec: append_note to "progress" with what was completed, files created/edited, and what spec is next.
11. If running low on message budget: STOP and append_note to "progress" with completed work, remaining work, current errors, and what the next session should do.

## Core Editing Rules
6. ALWAYS read a file before editing it. Never guess at file contents — even for files you created earlier in this session.
7. Use edit_file for targeted changes — provide the exact text to find (old_content) and its replacement (new_content).
8. CRITICAL: old_content and new_content must be the RAW file text. The read_file tool prepends line numbers like " 1 | code here" for display — NEVER include those line numbers or the " | " prefix in old_content or new_content. Use only the actual code.
9. The old_content must match EXACTLY once in the file. Include enough surrounding context to be unambiguous. If you get an ambiguous_anchor error, add more surrounding lines.
10. Be surgical — change only what's needed. Never rewrite entire files.
11. Never create files with placeholder or comment-only content. Every file must have real, functional code.

## Workflow: Vertical, Not Horizontal
12. Work depth-first. Create the first file, VERIFY it works, fix issues, then move to the next. Do NOT create all files at once.
13. After creating/editing a TypeScript file, run `npx tsc --noEmit` to check for type errors. Fix errors before moving on.
14. To test a server: use `run_command` with `background=true` to start it. This returns the PID and initial output without blocking. Then use `run_command` with `curl` to test endpoints. When done testing, use `stop_background` to kill the server. NEVER run a server with background=false — it will block for 60 seconds and waste your message budget.
15. If you create multiple files and discover one breaks the build, fix it before creating more. Do not move forward on a broken state.

## File Management
16. Use move_file to move/rename files. Use delete_file to remove files. Do not create empty files as workarounds.
17. After creating a file that imports from another package, verify the import path resolves correctly.

## Dependencies
18. When creating files that import external packages, ALWAYS install them first: `npm install <pkg>` from the project root (not from subdirectories — npm workspaces hoist to root).
19. For TypeScript projects: ALWAYS install @types/* alongside the main package. Example: `npm install express && npm install -D @types/express @types/node`.
20. To run TypeScript files: use `npx tsx <file>`. Install tsx first: `npm install -D tsx`. NEVER use `node` directly on .ts files.

## Framework Patterns (use these, not outdated patterns)
21. **React + Vite**: ALWAYS create index.html (with div#root and script type=module to /src/main.tsx) AND src/main.tsx (with createRoot). These are required — Vite cannot serve without them.
22. **React Router v6**: Use BrowserRouter, Routes, Route. NOT Switch (that's v5). BrowserRouter goes in ONE place only (App.tsx or main.tsx, not both).
23. **Express**: Always add `app.use(express.json())` for POST body parsing. Always add error handling middleware.
24. **sql.js**: db.exec() returns {{columns, values}} — raw arrays, NOT objects. ALWAYS map results to typed objects with camelCase field names (parent_id → parentId, created_at → createdAt).

## Error Recovery
25. When a command fails, read the error output carefully. Identify: 1) which file, 2) what line, 3) what the error is. Fix that specific issue.
26. If an edit fails twice with the same error, STOP and change your approach entirely. Do not retry the same edit.
27. If verification fails, fix the issue before creating more files. Errors compound when ignored.
28. If you cannot complete a file after 3 attempts, skip it. Write a note to .shipyard/notes/issues.md explaining what went wrong and what you tried. Move to the next file.

## Status Protocol (machine-read — do not skip)
29. ALWAYS end .shipyard/notes/progress.md with exactly one of these on its own line:
    - `STATUS: IN_PROGRESS` — more work remains from the plan
    - `STATUS: COMPLETE` — ALL specs/tasks are fully implemented and verified
    This line is read by the auto-continue system. If you omit it, the system assumes IN_PROGRESS and will re-run you.
30. BEFORE writing STATUS: COMPLETE, you MUST call verify_checklist. This tool checks that all files from your plan exist, servers start without crashing, and API endpoints respond. If any check fails, fix the issues first. Do NOT write STATUS: COMPLETE if verify_checklist reports failures.

## Reference Documents
31. Planning documents, specs, schemas, and PRDs may be in .shipyard/specs/, .shipyard/context/, docs/, or the project root. If you need reference material and can't find it, check ALL of these directories with read_file or list_files.
32. When the PRD or spec specifies package versions, install EXACT versions: `npm install express@4.21.2` not `npm install express`. Always include the @version suffix. Do NOT install latest — use the version from the spec.

## Finishing
33. Planning is NOT the end of the task. After writing a plan, IMMEDIATELY start implementing it. Only stop when all specs are implemented, or you run out of message budget.
34. When all implementation is truly complete: call verify_checklist → fix any failures → then write STATUS: COMPLETE to progress.md and stop.

Project root: {project_root}
"""


# --- Graph Construction ---

def create_agent_graph(config: ShipyardConfig, middleware: AgentMiddleware | None = None):
    """
    Create the single-agent LangGraph graph.

    This is the "direct mode" supervisor — no decomposition, no workers.
    The LLM has full tool access and loops until task completion.

    Args:
        config: ShipyardConfig with LLM and project settings
        middleware: Optional AgentMiddleware for logging/accounting

    Returns:
        A compiled LangGraph StateGraph ready to invoke
    """
    # 1. Set up LLM and tools
    llm = get_llm(config)
    registry = ToolRegistry(project_root=config.project_root)
    tools = registry.get_tools()
    model = llm.bind_tools(tools)

    # 2. Define nodes
    async def agent_node(state: AgentState) -> dict:
        """Call the LLM with current messages, with middleware hooks."""
        if middleware:
            await middleware.before_llm_call()

        messages = state["messages"]
        response = await model.ainvoke(messages)

        if middleware:
            # Extract token usage from response metadata if available
            usage = getattr(response, "usage_metadata", None) or {}
            middleware.after_llm_call(
                model=config.model_name,
                input_tokens=usage.get("input_tokens", 0) if isinstance(usage, dict) else getattr(usage, "input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0) if isinstance(usage, dict) else getattr(usage, "output_tokens", 0),
            )

        return {"messages": [response]}

    tool_node = ToolNode(tools)

    # 3. Define routing with smart circuit breaker
    def should_continue(state: AgentState) -> str:
        """Route to tools or end. Two-tier circuit breaker: hard limit + unproductive streak."""
        messages = state["messages"]

        # Hard gate: absolute max messages
        if len(messages) > HARD_MESSAGE_LIMIT:
            return "end"

        # Check if LLM wants to call tools
        last_message = messages[-1]
        if not (hasattr(last_message, "tool_calls") and last_message.tool_calls):
            return "end"

        # Soft gate: count consecutive unproductive turns
        # Walk backwards through messages to find recent tool results
        unproductive_streak = 0
        for msg in reversed(messages):
            if hasattr(msg, "name") and hasattr(msg, "content"):
                # This is a ToolMessage — check if the tool was productive
                tool_name = getattr(msg, "name", "")
                content = str(getattr(msg, "content", ""))
                if tool_name in PRODUCTIVE_TOOLS:
                    if content.startswith("✓"):
                        # Successful productive action — reset streak
                        break
                    else:
                        # Failed productive action (error) — count as unproductive
                        unproductive_streak += 1
                # Non-productive tools (read_file, list_files, etc.) don't affect the streak
            elif hasattr(msg, "tool_calls"):
                # LLM message with tool calls — skip
                continue
            else:
                # Regular LLM message — skip
                continue

            if unproductive_streak >= SOFT_UNPRODUCTIVE_LIMIT:
                return "end"

        return "tools"

    # 4. Build graph
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile()


async def run_agent(instruction: str, config: ShipyardConfig):
    """
    Run the agent on a single instruction.

    This is the main entry point for executing an instruction.
    It creates the graph, sets up the initial messages, and invokes.

    Args:
        instruction: The user's instruction
        config: ShipyardConfig

    Yields:
        Dict events from the graph execution for streaming:
        - {"type": "tool_call", "tool": name, "args": {...}}
        - {"type": "tool_result", "tool": name, "output": "..."}
        - {"type": "token", "content": "..."}
        - {"type": "done", "session_id": "..."}
    """
    # Set up session, context, and middleware
    session_mgr = SessionManager(config)
    session_id = session_mgr.start_session()
    context_mgr = ContextManager(config)
    middleware = AgentMiddleware(session_mgr, context_mgr, config)

    session_mgr.log_event(InstructionEvent(content=instruction))

    # Generate a run_id for trace linking
    run_id = str(uuid.uuid4())

    graph = create_agent_graph(config, middleware=middleware)

    system_msg = SystemMessage(content=SYSTEM_PROMPT.format(
        project_root=str(config.project_root)
    ))
    human_msg = HumanMessage(content=instruction)

    initial_state = {"messages": [system_msg, human_msg]}

    # Configure run with metadata for LangSmith
    # Set recursion_limit high — our custom circuit breaker handles stopping
    run_config = {
        "run_id": run_id,
        "recursion_limit": HARD_MESSAGE_LIMIT * 2,  # LangGraph recursion limit (graph steps, not messages)
        "metadata": {
            "session_id": session_id,
            "instruction": instruction[:200],
        },
        "tags": ["shipyard", "single-agent"],
    }

    # Stream graph execution
    async for event in graph.astream_events(initial_state, version="v2", config=run_config):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            # Streaming token from LLM
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                yield {"type": "token", "content": chunk.content}

        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            tool_input = event.get("data", {}).get("input", {})
            yield {"type": "tool_call", "tool": tool_name, "args": tool_input}

        elif kind == "on_tool_end":
            tool_name = event.get("name", "")
            tool_output = event.get("data", {}).get("output", "")
            # ToolMessage output can be a string or have .content
            if hasattr(tool_output, "content"):
                tool_output = tool_output.content
            output_str = str(tool_output)

            # Log tool call via middleware
            middleware.after_tool_call(
                tool_name,
                event.get("data", {}).get("input", {}),
                output_str,
            )

            yield {"type": "tool_result", "tool": tool_name, "output": output_str[:500]}

    # Build trace URL if tracing is enabled
    trace_url = ""
    if is_tracing_enabled():
        trace_url = get_trace_url(run_id, config)

    # Log task completion
    session_mgr.log_event(TaskCompleteEvent(summary="Task completed"))

    yield {"type": "done", "session_id": session_id, "trace_url": trace_url}


# --- Auto-Continue Loop ---

MAX_LOOP_ITERATIONS = 10


def _read_progress_file(config: ShipyardConfig) -> str:
    """Read .shipyard/notes/progress.md from disk. Returns empty string if not found."""
    progress_path = config.shipyard_path / "notes" / "progress.md"
    if progress_path.exists():
        return progress_path.read_text(encoding="utf-8")
    return ""


def _is_complete(progress_content: str) -> bool:
    """Check if progress.md signals completion."""
    return "STATUS: COMPLETE" in progress_content


def _save_context_files(config: ShipyardConfig, instruction: str) -> list[str]:
    """
    Extract context file contents from instruction and save to .shipyard/context/.
    Returns list of saved file paths (relative to project root).

    Context is appended by the CLI/server in this format:
    ---
    Attached context:
    <file contents>
    ---
    <file contents>
    """
    context_dir = config.shipyard_path / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    if "---\nAttached context:\n" not in instruction:
        return saved

    # Split out context block
    parts = instruction.split("---\nAttached context:\n", 1)
    if len(parts) < 2:
        return saved

    context_block = parts[1]
    # Each context file is separated by \n---\n
    chunks = context_block.split("\n---\n")

    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Try to detect filename from first line (e.g., "# SHIP-PRD.md")
        first_line = chunk.split("\n")[0]
        if first_line.startswith("# ") and ("." in first_line):
            # Extract filename from markdown header
            fname = first_line.lstrip("# ").strip().split(" ")[0]
            # Clean filename: "SHIP-PRD.md" -> keep, "—" and other chars -> strip
            fname = fname.split("—")[0].strip()
        else:
            fname = f"context_{i}.md"

        filepath = context_dir / fname
        filepath.write_text(chunk, encoding="utf-8")
        saved.append(str(filepath.relative_to(config.project_root)))

    return saved


def _get_context_file_listing(config: ShipyardConfig) -> str:
    """List saved context files for the continue message."""
    context_dir = config.shipyard_path / "context"
    if not context_dir.exists():
        return ""

    files = sorted(context_dir.glob("*.md"))
    if not files:
        return ""

    listing = "## Reference documents (saved from original context)\n"
    listing += "Read these files for specs, schemas, wireframes, and PRD details:\n"
    for f in files:
        rel = f.relative_to(config.project_root)
        listing += f"- {rel}\n"
    return listing


def _build_continue_message(
    original_instruction: str,
    progress_content: str,
    iteration: int,
    config: ShipyardConfig | None = None,
) -> str:
    """Build a deterministic continue message. No LLM call — pure string construction."""
    context_listing = ""
    if config:
        context_listing = _get_context_file_listing(config)

    return (
        f"Continue working on the original task. This is auto-continue iteration {iteration}.\n\n"
        f"## Original instruction\n{original_instruction[:2000]}\n\n"
        f"{context_listing}\n\n"
        f"## Current progress (from .shipyard/notes/progress.md)\n{progress_content}\n\n"
        "Resume from where you left off. Read .shipyard/notes/plan.md and progress.md for context. "
        "If you need spec details, read the reference documents listed above. "
        "Do NOT re-plan or re-do completed work. "
        "When ALL work is complete, update progress.md with STATUS: COMPLETE on its own line at the end."
    )


async def _post_completion_audit(config: ShipyardConfig) -> list[str]:
    """
    Run automated checks after agent claims STATUS: COMPLETE.
    Returns list of failure messages. Empty = all passed.
    """
    from shipyard.tools.verify import verify_checklist
    result_str = await verify_checklist(project_root=config.project_root)

    failures = []
    for line in result_str.split("\n"):
        if line.strip().startswith("✗"):
            failures.append(line.strip())

    return failures


def _override_progress_status(config: ShipyardConfig, failures: list[str]):
    """Override progress.md STATUS to IN_PROGRESS with audit failure details."""
    progress_path = config.shipyard_path / "notes" / "progress.md"
    if progress_path.exists():
        content = progress_path.read_text(encoding="utf-8")
        content = content.replace("STATUS: COMPLETE", "STATUS: IN_PROGRESS (overridden by audit)")
        content += "\n\n---\n**[AUDIT OVERRIDE]**\nThe following checks failed:\n"
        for f in failures:
            content += f"- {f}\n"
        content += "\nFix these issues and run verify_checklist again before marking complete.\n"
        content += "\nSTATUS: IN_PROGRESS\n"
        progress_path.write_text(content, encoding="utf-8")


async def run_agent_loop(instruction: str, config: ShipyardConfig):
    """
    Auto-continue wrapper around run_agent().

    Runs the agent, then checks .shipyard/notes/progress.md.
    If STATUS: COMPLETE is not found, constructs a continue message
    and re-runs. Max MAX_LOOP_ITERATIONS iterations.

    Yields the same event types as run_agent(), plus:
    - {"type": "continue", "iteration": N, "max": MAX_LOOP_ITERATIONS}

    Args:
        instruction: The user's original instruction
        config: ShipyardConfig

    Yields:
        Same dict events as run_agent, plus "continue" events between iterations
    """
    for iteration in range(1, MAX_LOOP_ITERATIONS + 1):
        # Determine the instruction for this iteration
        if iteration == 1:
            current_instruction = instruction
            # Save context files from the instruction to disk so they persist
            # across auto-continue iterations
            _save_context_files(config, instruction)
        else:
            progress_content = _read_progress_file(config)
            current_instruction = _build_continue_message(
                original_instruction=instruction,
                progress_content=progress_content,
                iteration=iteration,
                config=config,
            )

        # Run the agent for this iteration
        last_done_event = None
        async for event in run_agent(current_instruction, config):
            if event.get("type") == "done":
                last_done_event = event
                break  # Don't yield done yet — check if we should continue
            yield event

        # Check progress.md for STATUS: COMPLETE
        progress_content = _read_progress_file(config)
        if _is_complete(progress_content):
            # Agent claims done — run post-completion audit
            audit_failures = await _post_completion_audit(config)
            if not audit_failures:
                # All checks passed — truly done
                if last_done_event:
                    yield last_done_event
                return
            else:
                # Agent lied or missed something — override and continue
                yield {
                    "type": "continue",
                    "iteration": iteration + 1,
                    "max": MAX_LOOP_ITERATIONS,
                    "audit_failures": audit_failures,
                }
                # Override STATUS to IN_PROGRESS
                _override_progress_status(config, audit_failures)
                continue

        # Not complete — check if we have iterations remaining
        if iteration >= MAX_LOOP_ITERATIONS:
            # Max iterations reached — yield done and stop
            if last_done_event:
                yield last_done_event
            return

        # Yield continue event and loop (normal case — agent didn't claim complete)
        yield {
            "type": "continue",
            "iteration": iteration + 1,
            "max": MAX_LOOP_ITERATIONS,
        }


# --- Multi-Agent Orchestration ---

DECOMPOSE_PROMPT = """You are the Shipyard supervisor. Analyze this instruction and decide how to execute it.

If the task involves 2+ independent files that can be edited in parallel, decompose into subtasks.
If the task is simple (single file or tightly coupled changes), use direct mode.

Respond with valid JSON only:
{{
  "mode": "direct" | "parallel",
  "reasoning": "why you chose this mode",
  "subtasks": [
    {{
      "id": "unique-id",
      "instruction": "what this worker should do",
      "files_owned": ["path/to/file1.ts", "path/to/file2.ts"],
      "files_readable": ["path/to/shared.ts"]
    }}
  ],
  "shared_files": ["files no worker owns"]
}}

For "direct" mode, subtasks should be empty.
For "parallel" mode, ensure NO file appears in two workers' files_owned.

Project root: {project_root}

File listing:
{file_listing}
"""


async def decompose_task(
    instruction: str,
    config: ShipyardConfig,
) -> DecompositionResult:
    """
    Use the LLM to decompose an instruction into subtasks.

    The LLM decides whether to use direct mode (single agent)
    or parallel mode (multiple workers).

    Args:
        instruction: User's instruction
        config: ShipyardConfig

    Returns:
        DecompositionResult with mode and subtasks
    """
    from shipyard.tools.list_files import list_files

    # Get project file listing for context
    file_listing = await list_files(
        directory=".",
        depth=3,
        project_root=config.project_root,
    )

    llm = get_llm(config)
    messages = [
        SystemMessage(content=DECOMPOSE_PROMPT.format(
            project_root=str(config.project_root),
            file_listing=file_listing[:3000],
        )),
        HumanMessage(content=instruction),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Parse JSON from response
    try:
        # Try to extract JSON from the response
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        data = json.loads(json_str.strip())

        mode = TaskMode(data.get("mode", "direct"))
        subtasks = [
            Subtask(
                id=st.get("id", f"task-{i}"),
                instruction=st.get("instruction", ""),
                files_owned=st.get("files_owned", []),
                files_readable=st.get("files_readable", []),
            )
            for i, st in enumerate(data.get("subtasks", []))
        ]
        shared_files = data.get("shared_files", [])
        reasoning = data.get("reasoning", "")

        return DecompositionResult(
            mode=mode,
            subtasks=subtasks,
            shared_files=shared_files,
            reasoning=reasoning,
        )

    except (json.JSONDecodeError, ValueError, KeyError):
        # If parsing fails, fall back to direct mode
        return DecompositionResult(
            mode=TaskMode.DIRECT,
            subtasks=[],
            shared_files=[],
            reasoning="Failed to parse decomposition — falling back to direct mode",
        )


async def run_multi_agent(instruction: str, config: ShipyardConfig):
    """
    Multi-agent execution flow:
    1. Decompose instruction into subtasks
    2. If direct mode, fall through to run_agent (single-agent)
    3. If parallel mode:
       a. Dispatch workers via asyncio.gather
       b. Run merge agent for shared file edits
       c. Run project-wide validation
       d. Report results (or replan on failure)

    Yields same event types as run_agent, plus:
    - {"type": "decompose", "mode": "...", "subtasks": [...]}
    - {"type": "worker_start", "worker_id": "...", "instruction": "..."}
    - {"type": "worker_done", "worker_id": "...", "success": bool}
    - {"type": "merge", "results": {...}}
    - {"type": "validation", "passed": bool, "errors": [...]}

    Args:
        instruction: User's instruction
        config: ShipyardConfig

    Yields:
        Dict events for streaming
    """
    # Step 1: Decompose
    yield {"type": "status", "message": "Decomposing task..."}
    decomposition = await decompose_task(instruction, config)

    yield {
        "type": "decompose",
        "mode": decomposition.mode.value,
        "subtasks": [st.model_dump() for st in decomposition.subtasks],
        "shared_files": decomposition.shared_files,
        "reasoning": decomposition.reasoning,
    }

    # Step 2: Direct mode — fall through to single-agent
    if decomposition.mode == TaskMode.DIRECT or not decomposition.subtasks:
        yield {"type": "status", "message": "Using direct mode (single agent)"}
        async for event in run_agent_loop(instruction, config):
            yield event
        return

    # Step 3: Parallel mode — dispatch workers
    yield {
        "type": "status",
        "message": f"Dispatching {len(decomposition.subtasks)} workers in parallel",
    }

    orchestrator_state = OrchestratorState()

    # Import worker
    from shipyard.agent.worker import run_worker

    # Create worker coroutines
    worker_tasks = []
    for subtask in decomposition.subtasks:
        yield {
            "type": "worker_start",
            "worker_id": subtask.id,
            "instruction": subtask.instruction[:200],
            "files_owned": subtask.files_owned,
        }

        worker_tasks.append(
            run_worker(
                subtask_instruction=subtask.instruction,
                config=config,
                orchestrator_state=orchestrator_state,
                worker_id=subtask.id,
                files_owned=subtask.files_owned,
                files_readable=subtask.files_readable,
            )
        )

    # Dispatch all workers in parallel
    worker_results: list[WorkerResult] = await asyncio.gather(
        *worker_tasks,
        return_exceptions=True,
    )

    # Report worker results
    all_success = True
    for result in worker_results:
        if isinstance(result, Exception):
            yield {
                "type": "worker_done",
                "worker_id": "unknown",
                "success": False,
                "error": str(result),
            }
            all_success = False
        else:
            yield {
                "type": "worker_done",
                "worker_id": result.worker_id,
                "success": result.success,
                "files_modified": result.files_modified,
                "error": result.error,
            }
            if not result.success:
                all_success = False

    # Step 4: Merge agent — apply shared file edits
    if orchestrator_state.change_requests:
        yield {
            "type": "status",
            "message": f"Running merge agent for {len(orchestrator_state.change_requests)} shared file edits",
        }

        from shipyard.agent.merge_agent import run_merge_agent
        merge_results = await run_merge_agent(config, orchestrator_state)

        yield {
            "type": "merge",
            "results": {
                path: messages for path, messages in merge_results.items()
            },
        }
    else:
        yield {"type": "status", "message": "No shared file edits to merge"}

    # Step 5: Project-wide validation
    yield {"type": "status", "message": "Running project-wide validation..."}
    validation_passed, validation_errors = await _validate_project(config)

    yield {
        "type": "validation",
        "passed": validation_passed,
        "errors": validation_errors,
    }

    # Step 6: Report
    if validation_passed and all_success:
        yield {
            "type": "done",
            "session_id": "",
            "message": "Multi-agent task completed successfully",
        }
    else:
        # Collect all errors for reporting
        errors = validation_errors[:]
        for result in worker_results:
            if isinstance(result, WorkerResult) and result.error:
                errors.append(f"Worker {result.worker_id}: {result.error}")

        yield {
            "type": "done",
            "session_id": "",
            "message": f"Multi-agent task completed with errors: {'; '.join(errors[:5])}",
            "errors": errors,
        }


async def _validate_project(config: ShipyardConfig) -> tuple[bool, list[str]]:
    """
    Run project-wide validation after all workers and merge complete.

    Tries to run TypeScript type checking if the project has a tsconfig.json.
    Falls back to basic file existence checks.

    Returns:
        (passed: bool, errors: list[str])
    """
    from shipyard.tools.run_command import run_command
    from pathlib import Path

    errors = []
    project_root = config.project_root

    # Check for TypeScript project
    tsconfig = Path(project_root) / "tsconfig.json"
    if tsconfig.exists():
        result = await run_command(
            command="npx tsc --noEmit 2>&1 || true",
            working_directory=".",
            project_root=project_root,
        )
        if "error TS" in result:
            # Extract TypeScript errors
            for line in result.split("\n"):
                if "error TS" in line:
                    errors.append(line.strip())

    # Check package.json workspaces for monorepo
    pkg_json = Path(project_root) / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            if "workspaces" in pkg:
                # Check each workspace has its package.json
                for ws in pkg["workspaces"]:
                    ws_path = Path(project_root) / ws.rstrip("/*")
                    if ws_path.is_dir():
                        ws_pkg = ws_path / "package.json"
                        if not ws_pkg.exists():
                            errors.append(f"Workspace {ws} missing package.json")
        except (json.JSONDecodeError, KeyError):
            pass

    return len(errors) == 0, errors
