# Spec 05: CLI Client

## Objective
Create `shipyard/server/cli.py` — a thin CLI client that sends instructions to the FastAPI server and streams the response. This is the user-facing interface: `shipyard "do something"`.

## Dependencies
- Spec 01 (project scaffolding) must be complete
- Spec 04 (FastAPI server) must be complete

## File: `shipyard/server/cli.py`

### Design

Uses `click` for CLI argument parsing and `httpx` for HTTP + SSE streaming.

```python
import click
import httpx
import json
import sys


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


@click.group(invoke_without_command=True)
@click.argument("instruction", required=False)
@click.option("--base-url", default=DEFAULT_BASE_URL, envvar="SHIPYARD_URL", help="Server URL")
@click.option("--context", "-c", multiple=True, help="Attach context (file path or inline text)")
@click.option("--session", "-s", default=None, help="Resume a specific session ID")
@click.pass_context
def main(ctx, instruction, base_url, context, session):
    """Shipyard — autonomous coding agent.

    Send an instruction:  shipyard "add email validation to signup"
    With context:         shipyard "implement this spec" -c spec.md
    Session commands:     shipyard session list
    """
    ctx.ensure_object(dict)
    ctx.obj["base_url"] = base_url

    if instruction:
        _send_instruction(base_url, instruction, list(context), session)
    elif not ctx.invoked_subcommand:
        click.echo(ctx.get_help())


def _send_instruction(base_url: str, instruction: str, context_items: list[str], session_id: str | None):
    """POST instruction to /instruct and stream SSE response."""
    # Resolve context: if item is a file path, read it; otherwise use as-is
    resolved_context = []
    for item in context_items:
        try:
            with open(item, "r") as f:
                resolved_context.append(f.read())
        except (FileNotFoundError, IsADirectoryError):
            resolved_context.append(item)

    payload = {
        "instruction": instruction,
        "context": resolved_context if resolved_context else None,
        "session_id": session_id,
    }

    try:
        with httpx.stream(
            "POST",
            f"{base_url}/instruct",
            json=payload,
            timeout=httpx.Timeout(connect=5.0, read=300.0, write=5.0, pool=5.0),
        ) as response:
            if response.status_code != 200:
                click.echo(f"Error: server returned {response.status_code}", err=True)
                sys.exit(1)

            _stream_sse(response)

    except httpx.ConnectError:
        click.echo("Error: cannot connect to server. Is shipyard-server running?", err=True)
        click.echo(f"Tried: {base_url}", err=True)
        sys.exit(1)


def _stream_sse(response: httpx.Response):
    """Parse SSE stream and print events to stdout."""
    event_type = None

    for line in response.iter_lines():
        if not line:
            event_type = None
            continue

        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
            continue

        if line.startswith("data:"):
            data_str = line[len("data:"):].strip()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = {"raw": data_str}

            _handle_event(event_type, data)


def _handle_event(event_type: str | None, data: dict):
    """Display an SSE event to the user."""
    if event_type == "status":
        status = data.get("status", "")
        if status == "received":
            click.echo(f"→ {data.get('instruction', '')}")
        elif status == "complete":
            click.echo("\n✓ Done")
    elif event_type == "message":
        content = data.get("content", "")
        click.echo(content)
    elif event_type == "error":
        click.echo(f"✗ Error: {data.get('message', data)}", err=True)
    elif event_type == "done":
        pass  # handled by status complete
    else:
        # Unknown event type — print raw
        click.echo(json.dumps(data, indent=2))


# --- Session subcommands ---

@main.group()
@click.pass_context
def session(ctx):
    """Session management commands."""
    pass


@session.command("list")
@click.pass_context
def session_list(ctx):
    """List all sessions."""
    base_url = ctx.obj["base_url"]
    resp = httpx.get(f"{base_url}/session/list")
    sessions = resp.json().get("sessions", [])
    if not sessions:
        click.echo("No sessions found.")
    else:
        for s in sessions:
            click.echo(f"  {s['session_id']}  {s.get('status', '')}  {s.get('created_at', '')}")


@session.command("new")
@click.pass_context
def session_new(ctx):
    """Start a new session."""
    base_url = ctx.obj["base_url"]
    resp = httpx.post(f"{base_url}/session/new")
    data = resp.json()
    click.echo(f"New session: {data['session_id']}")


@session.command("info")
@click.argument("session_id")
@click.pass_context
def session_info(ctx, session_id):
    """Show session details."""
    base_url = ctx.obj["base_url"]
    resp = httpx.get(f"{base_url}/session/{session_id}")
    click.echo(json.dumps(resp.json(), indent=2))
```

## Implementation Notes

- The CLI uses `click.group` with `invoke_without_command=True` so that `shipyard "instruction"` works directly AND subcommands like `shipyard session list` also work
- Context items (`-c`): if the value is a valid file path, read the file; otherwise treat it as inline text
- SSE parsing is manual (line-by-line) because httpx doesn't have built-in SSE support. The format is simple enough: `event: <type>\ndata: <json>\n\n`
- Connection timeout is short (5s), but read timeout is long (300s) to allow for long-running agent tasks
- Error when server is unreachable: clear message telling user to start the server
- The `main` function is the entry point registered in `pyproject.toml` as the `shipyard` command

## Acceptance Criteria
- [ ] `shipyard "hello"` sends instruction and prints streamed response
- [ ] `shipyard "test" -c somefile.txt` reads file and attaches as context
- [ ] `shipyard "test" -c "inline context"` attaches inline text
- [ ] `shipyard session list` returns empty list
- [ ] `shipyard session new` creates and prints a session ID
- [ ] `shipyard` with no args prints help text
- [ ] Connection error gives a clear message about starting the server
- [ ] `shipyard --base-url http://localhost:9000 "test"` uses custom URL
- [ ] `SHIPYARD_URL=... shipyard "test"` reads URL from env var
