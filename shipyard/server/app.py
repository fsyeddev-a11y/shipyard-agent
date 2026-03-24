from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json

from shipyard.agent.supervisor import run_agent
from shipyard.config import get_config
from shipyard.session.manager import SessionManager
from shipyard.session.recovery import check_interrupted_sessions
from shipyard.tracing import setup_langsmith


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    config = get_config()
    # Ensure .shipyard directories exist
    config.sessions_path.mkdir(parents=True, exist_ok=True)
    config.notes_path.mkdir(parents=True, exist_ok=True)

    # Enable LangSmith tracing if configured
    tracing = setup_langsmith(config)
    if tracing:
        print(f"LangSmith tracing enabled (project: {config.langsmith_project})")
    else:
        print("LangSmith tracing disabled")

    # Check for interrupted sessions
    interrupted = check_interrupted_sessions(config)
    if interrupted:
        for info in interrupted:
            print(f"Warning: Interrupted session: {info.session_id} — last instruction: {info.last_instruction[:80]}")
    yield


app = FastAPI(title="Shipyard", version="0.1.0", lifespan=lifespan)


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
    Accept an instruction and stream the agent's response via SSE.
    """
    config = get_config()

    # Validate API key early
    if not config.openai_api_key:
        async def error_generator():
            yield {"event": "error", "data": json.dumps({"message": "SHIPYARD_OPENAI_API_KEY is not set"})}
            yield {"event": "done", "data": json.dumps({"status": "error"})}
        return EventSourceResponse(error_generator())

    async def event_generator():
        # Signal that we received the instruction
        yield {
            "event": "status",
            "data": json.dumps({"status": "received", "instruction": request.instruction})
        }

        instruction = request.instruction

        # If context was attached, prepend it to the instruction
        if request.context:
            context_block = "\n\n---\nAttached context:\n" + "\n---\n".join(request.context)
            instruction = instruction + context_block

        try:
            async for event in run_agent(instruction, config):
                event_type = event.get("type", "unknown")

                if event_type == "token":
                    yield {
                        "event": "message",
                        "data": json.dumps({"content": event["content"]})
                    }

                elif event_type == "tool_call":
                    yield {
                        "event": "tool_call",
                        "data": json.dumps({
                            "tool": event["tool"],
                            "args": event.get("args", {})
                        })
                    }

                elif event_type == "tool_result":
                    yield {
                        "event": "tool_result",
                        "data": json.dumps({
                            "tool": event["tool"],
                            "output": event.get("output", "")
                        })
                    }

                elif event_type == "done":
                    yield {
                        "event": "done",
                        "data": json.dumps({
                            "status": "complete",
                            "session_id": event.get("session_id", ""),
                            "trace_url": event.get("trace_url", ""),
                        })
                    }

                elif event_type == "error":
                    yield {
                        "event": "error",
                        "data": json.dumps({"message": event.get("message", "Unknown error")})
                    }

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)})
            }
            yield {
                "event": "done",
                "data": json.dumps({"status": "error"})
            }

    return EventSourceResponse(event_generator())


@app.post("/inject")
async def inject(request: InjectRequest):
    """
    Inject context into a running agent session.

    MVP: acknowledges the injection. Full integration requires sharing
    state with the running agent's context manager.
    """
    return {
        "status": "queued",
        "tier": request.tier,
        "label": request.label,
        "content_length": len(request.content),
    }


@app.get("/session/list")
async def session_list():
    """List all sessions from disk."""
    config = get_config()
    sm = SessionManager(config)
    sessions = sm.list_sessions()
    return {"sessions": sessions}


@app.post("/session/new")
async def session_new():
    """Create a new session."""
    import uuid
    return {"session_id": str(uuid.uuid4()), "status": "created"}


@app.get("/session/{session_id}")
async def session_get(session_id: str):
    """Get session details."""
    config = get_config()
    sm = SessionManager(config)
    events = sm.get_session_events(session_id)
    if not events:
        return {
            "session_id": session_id,
            "status": "not_found",
            "message": "Session not found",
        }
    return {
        "session_id": session_id,
        "status": "found",
        "event_count": len(events),
    }


@app.get("/session/{session_id}/export")
async def session_export(session_id: str):
    """Export a session as readable markdown."""
    config = get_config()
    sm = SessionManager(config)
    markdown = sm.export_session(session_id)
    return {"session_id": session_id, "export": markdown}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
