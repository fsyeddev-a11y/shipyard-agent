import json
import sys

import click
import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class ShipyardCLI(click.Group):
    """Custom group that treats unknown args as instructions."""

    def parse_args(self, ctx, args):
        # Separate known options/commands from the instruction text
        # Known options that take a value after them
        opts_with_value = {"--base-url", "-c", "--context", "-s", "--session"}
        opts_flags = {"--help"}

        instruction_parts = []
        remaining = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in opts_with_value and i + 1 < len(args):
                remaining.append(arg)
                remaining.append(args[i + 1])
                i += 2
            elif arg.startswith("-"):
                remaining.append(arg)
                i += 1
            elif arg in self.commands:
                # It's a subcommand — put it and everything after into remaining
                remaining.extend(args[i:])
                break
            else:
                instruction_parts.append(arg)
                i += 1

        if instruction_parts:
            ctx.params["_instruction"] = " ".join(instruction_parts)
        else:
            ctx.params["_instruction"] = None
        return super().parse_args(ctx, remaining)


@click.group(cls=ShipyardCLI, invoke_without_command=True)
@click.option("--base-url", default=DEFAULT_BASE_URL, envvar="SHIPYARD_URL", help="Server URL")
@click.option("--context", "-c", multiple=True, help="Attach context (file path or inline text)")
@click.option("--session", "-s", default=None, help="Resume a specific session ID")
@click.pass_context
def main(ctx, base_url, context, session, _instruction=None):
    """Shipyard — autonomous coding agent.

    Send an instruction:  shipyard "add email validation to signup"
    With context:         shipyard -c spec.md "implement this spec"
    Session commands:     shipyard session list
    Usage report:         shipyard usage --offline
    """
    ctx.ensure_object(dict)
    ctx.obj["base_url"] = base_url
    instruction = _instruction

    if ctx.invoked_subcommand:
        return
    if instruction:
        _send_instruction(base_url, instruction, list(context), session)
    else:
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
    elif event_type == "continue":
        iteration = data.get("iteration", "?")
        max_iter = data.get("max", "?")
        click.echo(f"\n--- Continuing... iteration {iteration}/{max_iter} ---\n")
    elif event_type == "error":
        click.echo(f"\n\u2717 Error: {data.get('message', data)}", err=True)
    elif event_type == "done":
        status = data.get("status", "")
        if status == "complete":
            click.echo("\n\u2713 Done")
            trace_url = data.get("trace_url", "")
            if trace_url:
                click.echo(f"  Trace: {trace_url}")
    else:
        # Unknown event type — print raw
        click.echo(json.dumps(data, indent=2))


# --- Usage subcommand ---


@main.command("usage")
@click.option("--detail", is_flag=True, help="Show per-session breakdown")
@click.option("--offline", is_flag=True, help="Read JSONL directly without server")
@click.option("--session-id", default=None, help="Filter to a specific session")
@click.pass_context
def usage_cmd(ctx, detail, offline, session_id):
    """Show token usage and cost report."""
    if offline:
        from shipyard.config import get_config as _get_config
        from shipyard.session.usage import calculate_usage

        config = _get_config()
        report = calculate_usage(config, session_id=session_id).model_dump()
    else:
        base_url = ctx.obj["base_url"]
        params = {}
        if session_id:
            params["session_id"] = session_id
        try:
            resp = httpx.get(f"{base_url}/usage", params=params)
            report = resp.json()
        except httpx.ConnectError:
            click.echo("Error: cannot connect to server. Use --offline to read directly.", err=True)
            sys.exit(1)

    _print_usage_report(report, detail=detail)


def _print_usage_report(report: dict, detail: bool = False):
    """Pretty-print a usage report."""
    click.echo("Shipyard Usage Report")
    click.echo("\u2500" * 37)
    click.echo(
        f"Sessions: {report['session_count']}    "
        f"LLM calls: {report['llm_call_count']}"
    )
    click.echo()

    # Per-model table
    by_model = report.get("by_model", [])
    if by_model:
        click.echo(f"{'Model':<15}{'Input':>10}{'Output':>10}{'Cost':>10}")
        for m in by_model:
            click.echo(
                f"{m['model']:<15}"
                f"{m['input_tokens']:>10,}"
                f"{m['output_tokens']:>10,}"
                f"{'$' + str(round(m['cost'], 2)):>10}"
            )
        click.echo()

    total_tokens = report["total_input_tokens"] + report["total_output_tokens"]
    click.echo(
        f"Total tokens: {total_tokens:,}    "
        f"Est. cost: ${report['total_cost']:.2f}"
    )
    click.echo("\u2500" * 37)

    if detail:
        click.echo()
        click.echo("Per-session breakdown:")
        for s in report.get("by_session", []):
            click.echo(
                f"  {s['session_id']}  "
                f"in={s['input_tokens']:,}  out={s['output_tokens']:,}  "
                f"calls={s['llm_calls']}  cost=${s['cost']:.2f}"
            )


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
