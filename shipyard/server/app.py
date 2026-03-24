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
