# Spec 06: Wire Phase 4 Into Agent Loop + Server

## Objective
Integrate the session manager, context manager, and middleware into the existing agent loop and server. This connects all the Phase 4 infrastructure to the running system.

## Dependencies
- Specs 01-05 of Phase 4 must be complete
- Phase 3 (agent loop, server) must be complete

## Changes Required

### 1. Update `shipyard/agent/supervisor.py`

The agent node needs to use the middleware before/after LLM calls, and the context manager for message assembly.

Key changes:
- Accept `SessionManager`, `ContextManager`, and `AgentMiddleware` as parameters to `create_agent_graph`
- In the `agent_node`: call `middleware.before_llm_call()` before invoking the LLM
- After LLM response: call `middleware.after_llm_call()` with token counts from the response metadata
- Integrate context manager: use `context_manager.assemble_messages()` instead of raw state messages for LLM input (or keep it simple for MVP — just wire in the middleware logging without changing message flow)

**MVP approach (recommended):** Keep the LangGraph message flow as-is (it works), but wrap it with middleware hooks for logging. Don't replace the message flow with the context manager yet — that's a bigger refactor. Instead:
- Log every LLM call via middleware
- Log every tool call via middleware
- Process injection queue before each LLM call
- Log session events (instruction, task_complete)

```python
# In create_agent_graph, the agent_node becomes:

async def agent_node(state: AgentState) -> dict:
    """Call the LLM with current messages, with middleware hooks."""
    await middleware.before_llm_call()

    messages = state["messages"]
    response = await model.ainvoke(messages)

    # Extract token usage from response metadata if available
    usage = getattr(response, "usage_metadata", None) or {}
    middleware.after_llm_call(
        model=config.model_name,
        input_tokens=usage.get("input_tokens", 0) if isinstance(usage, dict) else getattr(usage, "input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0) if isinstance(usage, dict) else getattr(usage, "output_tokens", 0),
    )

    return {"messages": [response]}
```

Note: Change `model.invoke` to `model.ainvoke` since we're now async.

### 2. Update `shipyard/agent/supervisor.py` — `run_agent`

- Create `SessionManager` and `ContextManager` at the start of `run_agent`
- Start a session and log the instruction event
- Pass them to `create_agent_graph`
- Log `TaskCompleteEvent` when agent finishes
- Yield session_id in the done event

```python
async def run_agent(instruction: str, config: ShipyardConfig):
    session_mgr = SessionManager(config)
    session_id = session_mgr.start_session()
    context_mgr = ContextManager(config)
    middleware = AgentMiddleware(session_mgr, context_mgr, config)

    session_mgr.log_event(InstructionEvent(content=instruction))

    # ... existing graph creation, but pass middleware ...

    # After streaming completes:
    session_mgr.log_event(TaskCompleteEvent(summary="Task completed"))
    yield {"type": "done", "session_id": session_id}
```

### 3. Update `shipyard/server/app.py`

Wire the real session endpoints:

```python
from shipyard.session.manager import SessionManager
from shipyard.session.recovery import check_interrupted_sessions

@app.get("/session/list")
async def session_list():
    config = get_config()
    sm = SessionManager(config)
    sessions = sm.list_sessions()
    return {"sessions": sessions}

@app.get("/session/{session_id}/export")
async def session_export(session_id: str):
    config = get_config()
    sm = SessionManager(config)
    markdown = sm.export_session(session_id)
    return {"session_id": session_id, "export": markdown}

@app.post("/inject")
async def inject(request: InjectRequest):
    # For MVP: just acknowledge. Full integration would push to the
    # running agent's context manager, but that requires sharing state
    # between the request handler and the running agent.
    # This will be properly wired when we have a persistent agent instance.
    return {
        "status": "queued",
        "tier": request.tier,
        "label": request.label,
        "content_length": len(request.content),
    }
```

### 4. Update `shipyard/server/app.py` — Startup

On server startup, check for interrupted sessions and log a warning:

```python
@app.on_event("startup")
async def startup_event():
    config = get_config()
    # Ensure .shipyard directories exist
    config.sessions_path.mkdir(parents=True, exist_ok=True)
    config.notes_path.mkdir(parents=True, exist_ok=True)

    # Check for interrupted sessions
    interrupted = check_interrupted_sessions(config)
    if interrupted:
        for info in interrupted:
            print(f"⚠ Interrupted session: {info.session_id} — last instruction: {info.last_instruction[:80]}")
```

## Implementation Notes

- **MVP approach**: Keep the existing LangGraph message flow. Add middleware as a logging/accounting wrapper. Don't replace message assembly with the context manager — that's a Phase 4+ optimization.
- The context manager's three-tier model and injection queue are implemented and ready but the full integration (replacing LangGraph's message handling) is deferred. The session logging and token accounting are the priority.
- `model.invoke` → `model.ainvoke` for proper async support with middleware
- Token counts from the LLM response depend on the provider. OpenRouter/LangChain's `ChatOpenAI` includes `usage_metadata` on the response object when available. Fall back to 0 if not present.

## Acceptance Criteria
- [ ] Agent loop logs LLMCallEvent for every LLM call with token counts
- [ ] Agent loop logs ToolCallEvent and ToolResultEvent for every tool call
- [ ] Session JSONL file created in `.shipyard/sessions/` for each instruction
- [ ] InstructionEvent and TaskCompleteEvent bookend each task
- [ ] `/session/list` returns real sessions from disk
- [ ] `/session/{id}/export` returns markdown export
- [ ] Interrupted sessions detected on server startup
- [ ] `.shipyard/sessions/` and `.shipyard/notes/` directories created on startup
- [ ] Middleware `before_llm_call` processes injection queue
