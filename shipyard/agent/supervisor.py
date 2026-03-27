from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

import uuid

from shipyard.agent.llm import get_llm
from shipyard.tools.registry import ToolRegistry
from shipyard.config import ShipyardConfig
from shipyard.session.manager import SessionManager
from shipyard.session.events import InstructionEvent, TaskCompleteEvent
from shipyard.context.manager import ContextManager
from shipyard.middleware.hooks import AgentMiddleware
from shipyard.tracing import is_tracing_enabled, get_trace_url


# --- State ---

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# --- System Prompt ---

SYSTEM_PROMPT = """You are Shipyard, an autonomous coding agent. You make surgical, targeted edits to codebases.

Rules:
1. ALWAYS read a file before editing it. Never guess at file contents.
2. Use edit_file for targeted changes — provide the exact text to find (old_content) and its replacement (new_content).
3. CRITICAL: old_content and new_content must be the RAW file text. The read_file tool prepends line numbers like " 1 | code here" for display — NEVER include those line numbers or the " | " prefix in old_content or new_content. Use only the actual code.
4. The old_content must match EXACTLY once in the file. Include enough surrounding context to be unambiguous. If you get an ambiguous_anchor error, add more surrounding lines.
5. For new files, use create_file.
6. After making changes, verify them by reading the file or running relevant commands.
7. Use search_files to find definitions, usages, and patterns across the codebase.
8. Use list_files to understand project structure before diving into files.
9. Be surgical — change only what's needed. Never rewrite entire files.
10. When you are done with all changes, stop. Do not keep talking — just confirm what you did.

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

    # 3. Define routing
    def should_continue(state: AgentState) -> str:
        """Route to tools or end. Includes circuit breaker."""
        if len(state["messages"]) > 50:
            return "end"  # circuit breaker
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "end"

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
    run_config = {
        "run_id": run_id,
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
