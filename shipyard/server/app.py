from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json

from shipyard.agent.supervisor import run_agent_loop
from shipyard.config import get_config
from shipyard.session.manager import SessionManager
from shipyard.session.recovery import check_interrupted_sessions
from shipyard.session.usage import calculate_usage
from shipyard.tracing import setup_langsmith

# Simple in-memory rate limiter
_rate_limit_store: dict[str, list[float]] = {}


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


# --- API Key Auth + Rate Limiting Middleware ---

@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    config = get_config()

    # Skip auth for health check
    if request.url.path == "/health":
        return await call_next(request)

    # API key check (only if api_secret is configured)
    if config.api_secret:
        provided_key = request.headers.get("X-Shipyard-Key", "")
        if provided_key != config.api_secret:
            raise HTTPException(status_code=401, detail="Invalid or missing API key. Set X-Shipyard-Key header.")

    # Rate limiting (only if api_secret is configured — i.e., deployed mode)
    if config.api_secret and request.url.path == "/instruct":
        now = time.time()
        hour_ago = now - 3600
        client = request.client.host if request.client else "unknown"

        if client not in _rate_limit_store:
            _rate_limit_store[client] = []

        # Clean old entries
        _rate_limit_store[client] = [t for t in _rate_limit_store[client] if t > hour_ago]

        if len(_rate_limit_store[client]) >= config.rate_limit_per_hour:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Max {config.rate_limit_per_hour} requests per hour.")

        _rate_limit_store[client].append(now)

    return await call_next(request)


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
            async for event in run_agent_loop(instruction, config):
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

                elif event_type == "continue":
                    evt_data = {
                        "iteration": event.get("iteration", 0),
                        "max": event.get("max", 10),
                    }
                    if event.get("audit_failures"):
                        evt_data["audit_failures"] = event["audit_failures"]
                    yield {
                        "event": "continue",
                        "data": json.dumps(evt_data),
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


@app.get("/usage")
async def usage(session_id: str | None = None):
    """Return aggregated token usage and cost report."""
    config = get_config()
    report = calculate_usage(config, session_id=session_id)
    return report.model_dump()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Simple web UI for the Shipyard agent."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Shipyard Agent</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,system-ui,sans-serif;background:#0a0a0f;color:#e5e5e5;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:2rem}
h1{font-size:2rem;font-weight:700;color:#3b82f6;margin-bottom:.25rem}
.sub{color:#9ca3af;margin-bottom:2rem}
.card{background:#111118;border:1px solid #1e1e2e;border-radius:12px;padding:1.5rem;width:100%;max-width:720px;margin-bottom:1rem}
.status{display:flex;align-items:center;gap:.5rem;margin-bottom:1rem}
.dot{width:10px;height:10px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
label{display:block;color:#9ca3af;font-size:.875rem;margin-bottom:.5rem}
textarea{width:100%;background:#0a0a0f;border:1px solid #2e2e3e;border-radius:8px;color:#e5e5e5;padding:.75rem;font-size:.875rem;resize:vertical;min-height:80px}
button{background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:.6rem 1.5rem;font-size:.875rem;cursor:pointer;margin-top:.75rem}
button:hover{background:#2563eb}
button:disabled{background:#1e3a5f;cursor:not-allowed}
#output{background:#0a0a0f;border:1px solid #2e2e3e;border-radius:8px;padding:1rem;max-height:400px;overflow-y:auto;font-family:monospace;font-size:.8rem;white-space:pre-wrap;color:#a3e635;display:none}
.tool{color:#60a5fa}.error{color:#f87171}.done{color:#22c55e;font-weight:700}
.info{color:#9ca3af;font-size:.8rem;margin-top:1rem}
</style>
</head>
<body>
<h1>Shipyard</h1>
<p class="sub">Autonomous Coding Agent</p>
<div class="card">
  <div class="status"><span class="dot"></span> Agent Running</div>
  <label>API Key</label>
  <input type="password" id="apiKey" placeholder="X-Shipyard-Key" style="width:100%;background:#0a0a0f;border:1px solid #2e2e3e;border-radius:8px;color:#e5e5e5;padding:.6rem;font-size:.875rem;margin-bottom:1rem">
  <label>Instruction</label>
  <textarea id="instruction" placeholder="e.g. Add a logout button to the navbar"></textarea>
  <button onclick="send()" id="btn">Send Instruction</button>
</div>
<div class="card"><div id="output"></div></div>
<div class="info">
  Surgical file editing &bull; Multi-agent coordination &bull; Git auto-commit &bull; LangSmith tracing<br>
  <a href="/docs" style="color:#3b82f6">API Docs</a> &bull; <a href="/health" style="color:#3b82f6">Health Check</a>
</div>
<script>
async function send(){
  const btn=document.getElementById('btn'),out=document.getElementById('output'),
    inst=document.getElementById('instruction').value,key=document.getElementById('apiKey').value;
  if(!inst)return;
  btn.disabled=true;btn.textContent='Running...';out.style.display='block';out.textContent='';
  try{
    const headers={'Content-Type':'application/json'};
    if(key)headers['X-Shipyard-Key']=key;
    const res=await fetch('/instruct',{method:'POST',headers,body:JSON.stringify({instruction:inst})});
    const reader=res.body.getReader(),decoder=new TextDecoder();
    let buf='';
    while(true){
      const{done,value}=await reader.read();
      if(done)break;
      buf+=decoder.decode(value,{stream:true});
      const lines=buf.split('\\n');buf=lines.pop();
      for(const line of lines){
        if(line.startsWith('data:')){
          try{
            const d=JSON.parse(line.slice(5));
            if(d.content)out.textContent+=d.content;
            else if(d.tool)out.innerHTML+='<span class="tool">\\n['+d.tool+']</span> ';
            else if(d.output)out.textContent+='\\n→ '+d.output.slice(0,200)+'\\n';
            else if(d.status==='complete')out.innerHTML+='<span class="done">\\n\\n✓ Done</span>';
            else if(d.message)out.innerHTML+='<span class="error">\\n'+d.message+'</span>';
          }catch{}
        }
      }
      out.scrollTop=out.scrollHeight;
    }
  }catch(e){out.innerHTML+='<span class="error">Error: '+e.message+'</span>'}
  btn.disabled=false;btn.textContent='Send Instruction';
}
</script>
</body>
</html>"""
