import json
import sys

import click
import httpx


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


def _send_instruction(
    base_url: str,
    instruction: str,
    context_items: list[str],
    session_id: str | None,
):
    """POST instruction to /instruct and stream SSE response."""
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
            click.echo(f"\u2192 {data.get('instruction', '')}")
        elif status == "complete":
            click.echo("\n\u2713 Done")
        elif status == "error":
            click.echo("\n\u2717 Completed with errors")
    elif event_type == "message":
        content = data.get("content", "")
        click.echo(content, nl=False)  # nl=False for streaming tokens
    elif event_type == "tool_call":
        tool = data.get("tool", "?")
        args = data.get("args", {})
        # Show a concise summary of the tool call
        args_summary = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
        click.echo(f"\n\U0001f527 {tool}({args_summary})")
    elif event_type == "tool_result":
        tool = data.get("tool", "?")
        output = data.get("output", "")
        # Show truncated output
        if len(output) > 200:
            output = output[:200] + "..."
        click.echo(f"   \u2192 {output}")
    elif event_type == "error":
        click.echo(f"\n\u2717 Error: {data.get('message', data)}", err=True)
    elif event_type == "done":
        pass  # handled by status
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
            click.echo(
                f"  {s['session_id']}  {s.get('status', '')}  {s.get('created_at', '')}"
            )


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
