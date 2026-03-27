# Spec 01: LangSmith Tracing

## Objective
Enable LangSmith tracing for the Shipyard agent. LangGraph traces automatically when the right environment variables are set. This spec wires everything up: env var setup at startup, run metadata tagging, and trace link extraction.

## Dependencies
- Phase 4 complete (agent loop with middleware)
- LangSmith account and API key

## How LangSmith + LangGraph Tracing Works

LangSmith tracing is activated by setting these **standard** environment variables (NOT prefixed with SHIPYARD_):

```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls-...
LANGCHAIN_PROJECT=shipyard
```

When these are set, LangGraph automatically traces:
- Every graph node execution
- Every LLM call (with full prompt and response)
- Every tool call (with inputs and outputs)
- Graph state transitions

No code changes to the graph are needed for basic tracing. The work here is:
1. Setting env vars from our config at startup
2. Adding metadata to runs (session_id, instruction)
3. Extracting trace link URLs
4. Logging trace links in the session and SSE stream

## Changes Required

### 1. Create `shipyard/tracing.py`

```python
import os
from shipyard.config import ShipyardConfig


def setup_langsmith(config: ShipyardConfig) -> bool:
    """
    Configure LangSmith tracing by setting environment variables.

    LangGraph reads these standard env vars directly — we bridge
    from our SHIPYARD_ prefixed config to the standard names.

    Call this once at server startup, before any LangGraph operations.

    Returns True if tracing is enabled, False otherwise.
    """
    if not config.langsmith_tracing or not config.langsmith_api_key:
        # Ensure tracing is disabled
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = config.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = config.langsmith_project

    return True


def get_trace_url(run_id: str, config: ShipyardConfig) -> str:
    """
    Construct a shareable LangSmith trace URL.

    Format: https://smith.langchain.com/o/<org>/projects/p/<project>/runs/<run_id>

    Since we may not know the org ID, use the simpler public share format
    or the direct run URL.
    """
    project = config.langsmith_project
    return f"https://smith.langchain.com/public/{run_id}/r"


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is currently active."""
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
```

### 2. Update `shipyard/server/app.py` — Startup

Add `setup_langsmith` call in the lifespan startup:

```python
from shipyard.tracing import setup_langsmith

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    # ... existing directory creation ...

    # Enable LangSmith tracing if configured
    tracing = setup_langsmith(config)
    if tracing:
        print(f"LangSmith tracing enabled (project: {config.langsmith_project})")
    else:
        print("LangSmith tracing disabled")

    # ... rest of existing startup ...
    yield
```

### 3. Update `shipyard/agent/supervisor.py` — Run Metadata + Trace Link

Add metadata to the graph invocation so traces are tagged with session_id and instruction. Extract the run_id for the trace link.

```python
from shipyard.tracing import is_tracing_enabled, get_trace_url
from langsmith import Client as LangSmithClient
import uuid

async def run_agent(instruction: str, config: ShipyardConfig):
    # ... existing setup ...

    # Generate a run_id for trace linking
    run_id = str(uuid.uuid4())

    graph = create_agent_graph(config, middleware=middleware)

    # ... existing message setup ...

    # Configure run with metadata for LangSmith
    run_config = {
        "run_id": run_id,
        "metadata": {
            "session_id": session_id,
            "instruction": instruction[:200],  # truncate for metadata
        },
        "tags": ["shipyard", "single-agent"],
    }

    # Stream graph execution with config
    async for event in graph.astream_events(initial_state, version="v2", config=run_config):
        # ... existing event handling ...

    # Build trace URL if tracing is enabled
    trace_url = ""
    if is_tracing_enabled():
        trace_url = get_trace_url(run_id, config)

    session_mgr.log_event(TaskCompleteEvent(summary="Task completed"))

    yield {"type": "done", "session_id": session_id, "trace_url": trace_url}
```

### 4. Update SSE + CLI to Show Trace Links

In `shipyard/server/app.py`, the done event already forwards `session_id`. Add `trace_url`:

```python
elif event_type == "done":
    yield {
        "event": "done",
        "data": json.dumps({
            "status": "complete",
            "session_id": event.get("session_id", ""),
            "trace_url": event.get("trace_url", ""),
        })
    }
```

In `shipyard/server/cli.py`, display the trace link:

```python
elif event_type == "done":
    pass  # handled by status
# Update the "status" handler:
if status == "complete":
    trace_url = data.get("trace_url", "")
    click.echo("\n✓ Done")
    if trace_url:
        click.echo(f"  Trace: {trace_url}")
```

### 5. Update `.env` Template

Add LangSmith vars to `.env`:

```
SHIPYARD_LANGSMITH_API_KEY=
SHIPYARD_LANGSMITH_PROJECT=gfa_shipyard
SHIPYARD_LANGSMITH_TRACING=false
```

## Trace Link Generation

LangSmith trace URLs follow this pattern:
- **Direct:** `https://smith.langchain.com/public/{run_id}/r` (if run is shared)
- **Project view:** Access via the LangSmith dashboard under the project name

For the MVP, we:
1. Pass `run_id` in the graph config so LangSmith uses it
2. Construct the URL from the run_id
3. Log it in the session and return it in the SSE stream
4. The user can also find traces in the LangSmith dashboard under the project

## Acceptance Criteria
- [ ] `setup_langsmith(config)` sets env vars when tracing is enabled
- [ ] `setup_langsmith(config)` returns False and clears env vars when disabled
- [ ] Server startup prints tracing status
- [ ] Agent runs appear in LangSmith when tracing is enabled
- [ ] Traces show graph nodes, LLM calls, and tool calls
- [ ] `run_id` is passed to graph invocation for trace linking
- [ ] Trace URL returned in the `done` SSE event
- [ ] CLI displays trace URL after completion
- [ ] `.env` has LangSmith config fields
- [ ] Tracing does NOT break the agent when disabled (no errors if no API key)
