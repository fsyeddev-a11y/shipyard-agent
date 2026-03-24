# Spec 04: FastAPI Server

## Objective
Create the FastAPI server that will host the agent. For Phase 1, all endpoints are stubs — they accept input and echo it back. The real agent loop gets wired in during Phase 3.

## Dependencies
- Spec 01 (project scaffolding) must be complete
- Spec 02 (config) must be complete

## File: `shipyard/server/app.py`

### Routes

```python
from fastapi import FastAPI
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

app = FastAPI(title="Shipyard", version="0.1.0")


# --- Request/Response Models ---

class InstructRequest(BaseModel):
    instruction: str
    context: list[str] | None = None  # optional attached context (specs, schemas)
    session_id: str | None = None     # resume existing session, or None for new


class InjectRequest(BaseModel):
    content: str
    tier: str = "tier2"               # "tier1" for critical, "tier2" for temporary
    label: str | None = None          # optional label for the context block


class SessionInfo(BaseModel):
    session_id: str
    created_at: str
    instruction_count: int
    status: str  # "active" | "completed" | "interrupted"


# --- Endpoints ---

@app.post("/instruct")
async def instruct(request: InstructRequest):
    """
    Accept an instruction and stream the response via SSE.

    Phase 1 stub: echoes the instruction back as a series of SSE events.
    Phase 3+: wires into the supervisor agent loop.
    """
    async def event_generator():
        # Stub: echo back the instruction in chunks
        yield {"event": "status", "data": json.dumps({"status": "received", "instruction": request.instruction})}

        await asyncio.sleep(0.1)  # simulate processing

        yield {"event": "message", "data": json.dumps({"content": f"Echo: {request.instruction}"})}

        if request.context:
            yield {"event": "message", "data": json.dumps({"content": f"Received {len(request.context)} context attachment(s)"})}

        yield {"event": "done", "data": json.dumps({"status": "complete"})}

    return EventSourceResponse(event_generator())


@app.post("/inject")
async def inject(request: InjectRequest):
    """
    Inject context into a running agent session.

    Phase 1 stub: acknowledges the injection.
    Phase 4+: adds to the context manager's injection queue.
    """
    return {
        "status": "queued",
        "tier": request.tier,
        "label": request.label,
        "content_length": len(request.content),
    }


@app.get("/session/list")
async def session_list():
    """List all sessions. Stub: returns empty list."""
    return {"sessions": []}


@app.post("/session/new")
async def session_new():
    """Create a new session. Stub: returns a mock session ID."""
    import uuid
    return {"session_id": str(uuid.uuid4()), "status": "created"}


@app.get("/session/{session_id}")
async def session_get(session_id: str):
    """Get session details. Stub: returns mock data."""
    return {
        "session_id": session_id,
        "status": "not_found",
        "message": "Session management not yet implemented",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
```

## File: `shipyard/main.py`

```python
import uvicorn
from shipyard.config import get_config


def run_server():
    """Entry point for `shipyard-server` command."""
    config = get_config()
    uvicorn.run(
        "shipyard.server.app:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
```

## Implementation Notes

- SSE streaming via `sse-starlette` — the `/instruct` endpoint returns an `EventSourceResponse`
- Three SSE event types: `status` (lifecycle), `message` (content), `done` (completion)
- All response data is JSON-serialized in the SSE `data` field
- The server is intentionally minimal — no middleware, no auth, no CORS (localhost only)
- The `/inject` endpoint is synchronous for now (returns immediately). In Phase 4, it will push to an async queue.

## Acceptance Criteria
- [ ] `shipyard-server` starts uvicorn on port 8000 (or configured port)
- [ ] `GET /health` returns `{"status": "ok", "version": "0.1.0"}`
- [ ] `POST /instruct` with `{"instruction": "hello"}` streams SSE events
- [ ] SSE stream includes `status`, `message`, and `done` events
- [ ] `POST /inject` returns acknowledgment with content length
- [ ] `GET /session/list` returns empty list
- [ ] `POST /session/new` returns a session ID
- [ ] Server stays alive after handling a request (persistent process)
- [ ] Can be tested with: `curl -N -X POST http://localhost:8000/instruct -H "Content-Type: application/json" -d '{"instruction":"test"}'`
