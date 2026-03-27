# Spec 04: Single Agent Loop (Supervisor Direct Mode)

## Objective
Create the single-agent LangGraph graph in `shipyard/agent/supervisor.py`. This is the supervisor in "direct" mode — it receives an instruction, reasons about it, calls tools, and loops until the task is complete. No multi-agent, no workers, no decomposition yet.

## Dependencies
- Spec 01 (tools) must be complete
- Spec 02 (tool registry) must be complete
- Spec 03 (LLM client) must be complete

## File: `shipyard/agent/supervisor.py`

### Design

A standard LangGraph ReAct agent: the LLM decides which tools to call, tools execute, results go back to the LLM, repeat until the LLM produces a final response (no more tool calls).

```python
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from pathlib import Path

from shipyard.agent.llm import get_llm
from shipyard.tools.registry import ToolRegistry
from shipyard.config import ShipyardConfig


# --- State ---

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# --- System Prompt ---

SYSTEM_PROMPT = """You are Shipyard, an autonomous coding agent. You make surgical, targeted edits to codebases.

Rules:
1. ALWAYS read a file before editing it. Never guess at file contents.
2. Use edit_file for targeted changes — provide the exact text to find (old_content) and its replacement (new_content).
3. The old_content must match EXACTLY once in the file. Include enough surrounding context to be unambiguous.
4. For new files, use create_file.
5. After making changes, verify them by reading the file or running relevant commands.
6. Use search_files to find definitions, usages, and patterns across the codebase.
7. Use list_files to understand project structure before diving into files.
8. Be surgical — change only what's needed. Never rewrite entire files.
9. Explain what you're doing and why before making changes.

Project root: {project_root}
"""


# --- Graph Construction ---

def create_agent_graph(config: ShipyardConfig) -> StateGraph:
    """
    Create the single-agent LangGraph graph.

    This is the "direct mode" supervisor — no decomposition, no workers.
    The LLM has full tool access and loops until task completion.

    Args:
        config: ShipyardConfig with LLM and project settings

    Returns:
        A compiled LangGraph StateGraph ready to invoke
    """
    # 1. Set up LLM and tools
    llm = get_llm(config)
    registry = ToolRegistry(project_root=config.project_root)
    tools = registry.get_tools()
    model = llm.bind_tools(tools)

    # 2. Define nodes
    def agent_node(state: AgentState) -> dict:
        """Call the LLM with the current message history."""
        messages = state["messages"]
        response = model.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    # 3. Define routing
    def should_continue(state: AgentState) -> str:
        """Route to tools if the LLM made tool calls, otherwise end."""
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
        - {"type": "message", "content": "..."}
        - {"type": "done", "summary": "..."}
    """
    graph = create_agent_graph(config)

    system_msg = SystemMessage(content=SYSTEM_PROMPT.format(
        project_root=str(config.project_root)
    ))
    human_msg = HumanMessage(content=instruction)

    initial_state = {"messages": [system_msg, human_msg]}

    # Stream graph execution
    async for event in graph.astream_events(initial_state, version="v2"):
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
            yield {"type": "tool_result", "tool": tool_name, "output": str(tool_output)[:500]}

    # Final message
    yield {"type": "done"}
```

### Implementation Notes

- **LangGraph ReAct pattern:** agent → should_continue → tools → agent → ... → END
- `ToolNode` from `langgraph.prebuilt` handles tool execution automatically — it reads `tool_calls` from the AI message, executes the matching tools, and returns `ToolMessage` results
- `add_messages` annotation on the state handles message accumulation correctly
- The system prompt is critical — it tells the LLM how to use the tools properly. The "read before edit" rule prevents stale-context errors.
- `run_agent` is an async generator that yields streaming events. The server (spec 05) will consume these and forward them as SSE.
- `astream_events` with `version="v2"` gives us granular events for each node, tool call, and LLM token
- Tool output is truncated to 500 chars in the yielded event (the full output still goes to the LLM via the message history)
- The graph has no iteration limit built in — add a maximum of 25 iterations (tool call rounds) as a safety circuit breaker. If the agent hasn't finished after 25 rounds, yield an error event and stop.

### Circuit Breaker

Add a max iterations check. The simplest approach: count messages in state. If `len(messages) > 50` (roughly 25 LLM turns), force stop.

```python
def should_continue(state: AgentState) -> str:
    """Route to tools or end. Includes circuit breaker."""
    if len(state["messages"]) > 50:
        return "end"  # circuit breaker
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"
```

## Acceptance Criteria
- [ ] `from shipyard.agent.supervisor import create_agent_graph, run_agent` works
- [ ] `create_agent_graph(config)` returns a compiled LangGraph graph
- [ ] Graph has "agent" and "tools" nodes with correct edges
- [ ] `run_agent` is an async generator yielding event dicts
- [ ] System prompt includes project root and tool usage rules
- [ ] Circuit breaker stops execution after too many iterations
- [ ] Events include tool_call, tool_result, token, and done types
