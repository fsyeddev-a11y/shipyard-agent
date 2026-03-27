# Spec 05: Wire Server to Agent Loop

## Objective
Update `shipyard/server/app.py` to connect the `/instruct` endpoint to the real agent loop instead of the echo stub. Agent events are streamed to the client as SSE.

## Dependencies
- Spec 04 (single agent loop) must be complete
- Phase 1 server (app.py) must be the base

## File: `shipyard/server/app.py` (modify existing)

### Changes Required

Replace the echo stub in the `/instruct` endpoint with a call to `run_agent`. The agent's yielded events get forwarded as SSE events to the client.

```python
from shipyard.agent.supervisor import run_agent
from shipyard.config import get_config
import json

# ... existing imports and models stay the same ...

@app.post("/instruct")
async def instruct(request: InstructRequest):
    """
    Accept an instruction and stream the agent's response via SSE.
    """
    config = get_config()

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
                        "data": json.dumps({"status": "complete"})
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
```

### CLI Updates (`shipyard/server/cli.py`)

Update `_handle_event` to display the new event types:

```python
def _handle_event(event_type: str | None, data: dict):
    """Display an SSE event to the user."""
    if event_type == "status":
        status = data.get("status", "")
        if status == "received":
            click.echo(f"→ {data.get('instruction', '')}")
        elif status == "complete":
            click.echo("\n✓ Done")
        elif status == "error":
            click.echo("\n✗ Completed with errors")
    elif event_type == "message":
        content = data.get("content", "")
        click.echo(content, nl=False)  # nl=False for streaming tokens
    elif event_type == "tool_call":
        tool = data.get("tool", "?")
        args = data.get("args", {})
        # Show a concise summary of the tool call
        args_summary = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
        click.echo(f"\n🔧 {tool}({args_summary})")
    elif event_type == "tool_result":
        tool = data.get("tool", "?")
        output = data.get("output", "")
        # Show truncated output
        if len(output) > 200:
            output = output[:200] + "..."
        click.echo(f"   → {output}")
    elif event_type == "error":
        click.echo(f"\n✗ Error: {data.get('message', data)}", err=True)
    elif event_type == "done":
        pass  # handled by status
    else:
        click.echo(json.dumps(data, indent=2))
```

### Graceful Fallback

If `SHIPYARD_OPENROUTER_API_KEY` is not set, the `/instruct` endpoint should return a clear error via SSE instead of crashing:

```python
try:
    config = get_config()
    # Validate API key early
    if not config.openrouter_api_key:
        async def error_generator():
            yield {"event": "error", "data": json.dumps({"message": "SHIPYARD_OPENROUTER_API_KEY is not set"})}
            yield {"event": "done", "data": json.dumps({"status": "error"})}
        return EventSourceResponse(error_generator())
except Exception as e:
    # ...
```

### Keep Existing Endpoints

All other endpoints (`/inject`, `/session/*`, `/health`) remain unchanged. They're still stubs — they'll be wired in during Phase 4.

## Acceptance Criteria
- [ ] `/instruct` now invokes the real agent loop (not echo stub)
- [ ] SSE stream includes: `status`, `tool_call`, `tool_result`, `message`, `done` events
- [ ] Attached context is prepended to the instruction
- [ ] Missing API key returns a clear error event (not a crash)
- [ ] Exceptions during agent execution are caught and sent as error events
- [ ] CLI displays tool calls and results with formatting
- [ ] `GET /health` still works (other endpoints unchanged)
- [ ] End-to-end test: start server → `shipyard "list the files in this project"` → shows tool calls and file listing
