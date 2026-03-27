# Shipyard

An autonomous coding agent that makes surgical file edits, runs as a persistent server, and coordinates complex multi-file changes through natural language instructions.

Built with LangGraph (Python), FastAPI, and OpenAI. Every edit uses anchor-based replacement with unified diff verification and automatic git commits. All runs are traced via LangSmith.

## Architecture

```
User (CLI) → FastAPI Server → Session Manager → Agent (LangGraph ReAct) → Tools → Edit Engine → Git
                                                      ↓
                                                 LLM (OpenAI API)
                                                      ↓
                                             SSE stream → CLI output
```

**Agent loop:** LangGraph StateGraph with a ReAct pattern — the LLM reasons about the task, calls tools, observes results, and loops until done. A circuit breaker prevents runaway execution.

**Edit engine:** Every file edit goes through a deterministic pipeline: find anchor (exact match, must appear once) → normalize whitespace → replace → compute unified diff → verify diff stays within anchor boundaries → write file → git auto-commit. If any step fails, the file is never written.

**Session logging:** All events (instructions, tool calls, edits, LLM calls with token counts) are logged to append-only JSONL files for full auditability and cost tracking.

## Stack

| Component | Technology |
|-----------|-----------|
| Agent loop | LangGraph (Python) |
| Server | FastAPI with SSE streaming |
| LLM | OpenAI API (gpt-4o default, swappable via env var) |
| Tracing | LangSmith |
| Storage | JSONL sessions, markdown notes |
| CLI | Click + httpx |

## Setup

```bash
# Clone and install
git clone https://labs.gauntletai.com/faheemsyed/shipyard.git
cd shipyard
pip install -e ".[dev]"

# Configure (create .env in project root)
SHIPYARD_OPENAI_API_KEY=sk-...
SHIPYARD_MODEL_NAME=gpt-4o
SHIPYARD_LANGSMITH_API_KEY=ls-...        # optional
SHIPYARD_LANGSMITH_PROJECT=gfa_shipyard  # optional
SHIPYARD_LANGSMITH_TRACING=true          # optional
```

## Usage

**Start the server from your target project directory:**
```bash
cd /path/to/your/project
python3.12 -m shipyard.main
```

The server runs on `http://127.0.0.1:8000`. The agent operates on whatever directory the server is started from.

**Send instructions from a second terminal (same directory):**
```bash
cd /path/to/your/project
shipyard "Add input validation to the createUser function"
```

**Attach context files:**
```bash
shipyard -c style-guide.md "Refactor the auth module following the attached style guide"
```

**Session and usage commands:**
```bash
shipyard session list
shipyard usage --offline
shipyard usage --detail
```

## Tools

The agent has 7 tools, each async with Pydantic input schemas:

| Tool | Purpose |
|------|---------|
| `read_file` | Read file contents with line numbers, optional line range |
| `edit_file` | Surgical anchor-based replacement with diff verification |
| `edit_file_multi` | Atomic multi-site edits (all succeed or none applied) |
| `create_file` | Create new files with auto-commit |
| `list_files` | Directory tree with configurable depth |
| `search_files` | Grep/ripgrep pattern search across codebase |
| `run_command` | Shell command execution with timeout and output truncation |

## Edit Engine

The core of Shipyard. Every edit follows this pipeline:

1. **Find anchor** — `old_content` must match exactly once in the file
2. **Normalize** — detect file's whitespace conventions, normalize `new_content` to match
3. **Replace** — substitute `old_content` with normalized `new_content`
4. **Diff** — compute unified diff between original and modified
5. **Verify** — all diff hunks must fall within the anchor's line span
6. **Write** — only written to disk if verification passes
7. **Git commit** — automatic commit with descriptive message

Multi-edits (`edit_file_multi`) validate all anchors first (all-or-nothing), apply replacements bottom-to-top to prevent position drift, then make a single git commit.

## Test Suite

```bash
# Layer 1 + 2: Edit engine + tools (fast, no LLM)
pytest tests/test_edit_engine.py tests/test_tools.py tests/test_git_helpers.py -v

# Layer 3: Agent evals (live LLM, ~100s)
pytest tests/evals/ -v --timeout=180
```

| Layer | Tests | What It Covers |
|-------|-------|---------------|
| Layer 1 — Edit Engine | 36 | Anchor matching, diff verification, atomicity, edge cases |
| Layer 2 — Tools | 10 | Each tool against known filesystem state |
| Layer 3 — Agent Evals | 10 | End-to-end: single edit, multi-file, search+edit, error handling, context injection, large files, file precision |

## Project Structure

```
shipyard/
├── shipyard/
│   ├── agent/           # LLM client, supervisor graph
│   ├── edit_engine/     # Anchor matching, diff, normalize, git
│   ├── tools/           # read_file, edit_file, create_file, etc.
│   ├── server/          # FastAPI app, CLI client
│   ├── session/         # JSONL logging, events, usage tracking
│   ├── context/         # Three-tier context manager, tokens
│   ├── middleware/       # Before/after LLM call hooks
│   ├── config.py        # Pydantic Settings, env vars
│   ├── tracing.py       # LangSmith setup
│   └── main.py          # Uvicorn entry point
├── tests/
│   ├── evals/           # Layer 3 agent evals
│   ├── test_edit_engine.py
│   ├── test_tools.py
│   └── test_git_helpers.py
├── docs/                # Phase specs and planning
└── pyproject.toml
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/instruct` | POST | Send instruction, streams SSE response |
| `/inject` | POST | Inject context into running session |
| `/health` | GET | Health check |
| `/usage` | GET | Token usage and cost report |
| `/session/list` | GET | List all sessions |
| `/session/{id}` | GET | Get session details |
| `/session/{id}/export` | GET | Export session as markdown |

## Configuration

All config via environment variables (prefix `SHIPYARD_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SHIPYARD_OPENAI_API_KEY` | (required) | OpenAI API key |
| `SHIPYARD_MODEL_NAME` | `gpt-4o` | Model to use |
| `SHIPYARD_HOST` | `127.0.0.1` | Server host |
| `SHIPYARD_PORT` | `8000` | Server port |
| `SHIPYARD_LANGSMITH_TRACING` | `false` | Enable LangSmith |
| `SHIPYARD_COST_PER_MILLION_INPUT` | `2.50` | Cost tracking |
| `SHIPYARD_COST_PER_MILLION_OUTPUT` | `10.00` | Cost tracking |
