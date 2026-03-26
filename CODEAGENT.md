# CODEAGENT.md — Shipyard Coding Agent

## Agent Architecture

### System Overview

Shipyard is a single-agent system (MVP) built on LangGraph + FastAPI. A persistent FastAPI server accepts natural language instructions via HTTP, runs a LangGraph ReAct agent loop, and streams results back via Server-Sent Events (SSE). A thin CLI client (`shipyard "instruction"`) wraps the HTTP calls.

```
User (CLI) → FastAPI Server → Session Manager → Agent (LangGraph ReAct) → Tools → Edit Engine → Git
                                                       ↓
                                                  LLM (OpenAI API)
                                                       ↓
                                              SSE stream → CLI output
```

### Agent Loop

The agent is a LangGraph `StateGraph` with two nodes in a standard ReAct pattern:

| Node | Implementation | Purpose |
|------|---------------|---------|
| `agent` | Async function calling `model.ainvoke(messages)` | LLM reasoning — decides which tools to call or produces final response |
| `tools` | `langgraph.prebuilt.ToolNode` | Executes tool calls from the LLM response, returns results as `ToolMessage` |

**Routing:** After the `agent` node, a `should_continue` function checks whether the LLM's response contains tool calls. If yes → route to `tools`. If no → route to `END`. A circuit breaker stops execution if message count exceeds 50 (roughly 25 LLM turns).

**State schema:**

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

Messages accumulate via LangGraph's `add_messages` reducer. The full conversation history (system prompt, user instruction, LLM responses, tool calls, tool results) is maintained in state and passed to the LLM on each turn.

### LLM Integration

The LLM is OpenAI's API accessed via `langchain-openai`'s `ChatOpenAI`. Model is configurable via `SHIPYARD_MODEL_NAME` env var (default: `gpt-4o`). Temperature is 0 for deterministic coding output. Tools are bound to the model via `model.bind_tools(tools)`.

### System Prompt

The agent operates under a system prompt that enforces surgical editing discipline:

1. Always read a file before editing it
2. Use `edit_file` with exact `old_content` matching
3. Include enough surrounding context for unambiguous anchors
4. Use `create_file` for new files only
5. Verify changes after making them
6. Use `search_files` for discovery before editing
7. Use `list_files` to understand project structure first
8. Be surgical — change only what's needed
9. Explain reasoning before making changes

### Tool Suite

Seven tools are registered via `ToolRegistry`, which pre-injects `project_root` so the LLM doesn't see or control it:

| Tool | Input | Output | Implementation |
|------|-------|--------|---------------|
| `read_file` | `file_path`, optional `start_line`/`end_line` | File contents with line numbers prepended (`N \| line`) | Direct file read, line-number formatting |
| `edit_file` | `file_path`, `old_content`, `new_content`, `description` | Success with diff summary, or error with context | Delegates to `edit_engine.apply_edit()` |
| `edit_file_multi` | `file_path`, `edits` (list of old/new pairs), `description` | Success or atomic failure | Delegates to `edit_engine.apply_edit_multi()` |
| `create_file` | `file_path`, `content` | Success or error if file exists | Creates parent dirs, writes file, git commits |
| `list_files` | `directory`, `depth` | Tree-format directory listing | Walks filesystem, skips `.git`/`node_modules`/`.shipyard` |
| `search_files` | `pattern`, `directory`, `file_glob` | Matching lines with `file:line: content` format | Uses `rg` (ripgrep) or falls back to `grep -rn` |
| `run_command` | `command`, `working_directory` | stdout + stderr with exit code | `asyncio.create_subprocess_shell`, 60s timeout, output truncated at 200 lines |

All tools are async, return strings (never raise to the LLM), and have Pydantic `Input` models for schema generation.

**File ownership enforcement** is built into `ToolRegistry` for future multi-agent use: when `files_owned` is set, edit/create tools check the file path and return an error string if the file isn't owned by the worker. In single-agent mode (`files_owned=None`), no restrictions apply.

### Middleware

Deterministic hooks run before/after each LLM call — these are NOT agentic, they always execute:

**Before each LLM call (`before_llm_call`):**
- Process injection queue (check for `/inject` context)
- Enforce context budget (evict Tier 3 if over threshold)
- Start timing for duration tracking

**After each LLM call (`after_llm_call`):**
- Log `LLMCallEvent` with token counts, cost estimate, and duration
- Token counts extracted from `response.usage_metadata`

**After each tool call (`after_tool_call`):**
- Log `ToolCallEvent` and `ToolResultEvent`
- Detect edit tool success → log `EditEvent` with diff summary and commit hash

### Context Management

Three-tier model for prompt assembly:

| Tier | Contents | Management | Budget |
|------|----------|------------|--------|
| Tier 1: Pinned | System prompt, project root | Append-only, never evicted | ~10k tokens |
| Tier 2: Containers | Named blocks (errors, active files, notes index) | Agent adds/removes via `set()`/`remove()` | ~30k tokens |
| Tier 3: Sliding | Conversation history, tool results, file contents | Recency-based eviction (oldest first) | Remainder (~120k for gpt-4o) |

**Budget enforcement:** Before each LLM call, total tokens are tallied. If above 80% of the model's context window, Tier 3 eviction begins. Eviction is **non-destructive** — entries are marked `evicted=True` but remain in the list for session logging.

**Injection queue:** The `/inject` endpoint pushes context to an `asyncio.Queue`. Middleware calls `process_injection_queue()` before each LLM call, adding injected content to the appropriate tier.

Token counting uses `tiktoken` with `cl100k_base` encoding as an approximation.

### Session Management

Every agent action is logged to `/.shipyard/sessions/{session_id}.jsonl` — one JSON line per event. 14 event types:

```
session_start, instruction, plan, tool_call, tool_result, edit,
llm_call, context_evicted, context_injected, task_complete,
worker_dispatched, worker_completed, worker_failed, error
```

The `llm_call` event includes token counts (`input`, `output`, `cache_read`), cost estimate, and duration — required for cost analysis.

**Session lifecycle:** Server starts → session manager initializes → user sends instruction → new session created → events logged → task completes → session stays open for next instruction.

**Crash recovery:** On startup, the server scans session logs for interrupted sessions (instruction without matching task_complete) and prints warnings.

**Session endpoints:**
- `GET /session/list` — all sessions with metadata and status
- `GET /session/{id}` — session details
- `GET /session/{id}/export` — markdown export with tool calls, edits, and token summary
- `POST /session/new` — create a new session

### Observability

LangSmith tracing is enabled by setting `SHIPYARD_LANGSMITH_TRACING=true` and providing an API key. The server bridges `SHIPYARD_*` config to standard `LANGCHAIN_*` env vars at startup.

Every agent run is tagged with a `run_id` (UUID), `session_id`, and instruction metadata. LangGraph traces automatically — every graph node, LLM call, and tool invocation appears in LangSmith. The trace URL is returned in the `done` SSE event and displayed by the CLI.

### Server Architecture

FastAPI with `sse-starlette` for streaming. The server is a persistent process — it stays alive between instructions.

**Endpoints:**
- `POST /instruct` — main endpoint, accepts instruction + optional context, streams agent events as SSE
- `POST /inject` — inject context into a running session (MVP: acknowledgment stub)
- `GET /health` — health check
- Session endpoints (list, get, export, new)

**SSE event types:** `status`, `message` (streaming tokens), `tool_call`, `tool_result`, `error`, `done`

**CLI:** Thin `click` + `httpx` client. Sends POST to `/instruct`, parses SSE stream, displays tool calls with args, streaming LLM output, and trace URL on completion.

---

## File Editing Strategy

### Primary Mechanism: Anchor-Based Replacement

The edit engine (`shipyard/edit_engine/engine.py`) is deterministic Python — no LLM calls. It takes `file_path`, `old_content`, `new_content` and executes a 6-step pipeline:

**Step 1 — Read:** Read the file from disk as `original_content`.

**Step 2 — Find anchor:** Count occurrences of `old_content` in `original_content`.
- 0 matches → return `anchor_not_found` error with the first 100 lines as context (so the LLM can see what's actually there and retry)
- 2+ matches → return `ambiguous_anchor` error with match count (LLM needs to include more surrounding context)
- 1 match → record the anchor's start and end line numbers (0-based, in original file coordinates)

**Step 3 — Normalize:** Detect the file's whitespace conventions (tabs vs spaces, indent size, line endings) and normalize `new_content` to match. Trailing whitespace is stripped per line. A trailing-newline parity fix preserves the anchor's newline behavior (prevents injecting extra newlines into mid-file fragments).

**Step 4 — Replace:** `original_content.replace(old_content, normalized_new, 1)` → `modified_content`

**Step 5 — Verify:** Compute unified diff between original and modified. Parse diff hunks and verify:
- All hunks fall within the anchor span ± 3 context lines (using **old-file line numbers** — new-file line numbers shift when block size changes)
- Total changed lines under threshold (default: 100 for single edits, 200 for multi)
- If verification fails → do NOT write the file. Return the diff and reason.

**Step 6 — Commit:** Write `modified_content` to disk. Git commit with message `"shipyard: edit: {file_path} — {description}"`. Return `EditResult` with diff summary and commit hash.

### Multi-Edit: `apply_edit_multi`

For multiple edits to the same file, `apply_edit_multi` provides atomicity:

1. **Validation pass:** Check ALL anchors for existence and uniqueness before applying any edits. If any anchor fails → return error, no edits applied.
2. **Sort descending:** Order edits by character offset, bottom-of-file first. This ensures earlier replacements don't shift positions of later anchors.
3. **Apply all:** Execute replacements in bottom-to-top order.
4. **Single diff + single commit:** One unified diff computed for the combined result, one git commit for the batch.

### Whitespace Normalization

The normalize module (`shipyard/edit_engine/normalize.py`) detects:
- **Indentation style:** Counts lines starting with tabs vs spaces. If spaces win, detects indent size via GCD of leading space counts.
- **Line endings:** Counts `\r\n` vs `\n`, majority wins.

Normalization converts `new_content` to match: tabs↔spaces, line endings, strip trailing whitespace, ensure single trailing newline.

### Diff Verification

The diff module (`shipyard/edit_engine/diff.py`) uses `difflib.unified_diff` for diff computation and a regex parser for `@@ -old_start,count +new_start,count @@` hunk headers.

Verification uses **old-file line numbers** because the new file's line numbers shift when the replacement changes block size. The anchor span is expanded by `context_lines` (default 3) to account for `difflib`'s surrounding context.

### Git Integration

Every validated edit triggers an automatic git commit via `shipyard/edit_engine/git.py`. This is non-negotiable — it's the rollback mechanism. Functions:
- `git_init_if_needed` — ensures a repo exists with an initial commit
- `git_commit` — stages and commits a single file with `"shipyard: "` prefix
- `git_commit_files` — stages and commits multiple files (for multi-edit batches)
- `git_revert_last` — creates revert commits (non-destructive, doesn't rewrite history)

### Error Handling

| Error | Detection | Recovery |
|-------|-----------|----------|
| Anchor not found | `str.count()` returns 0 | Return first 100 lines as context for LLM retry |
| Ambiguous anchor | `str.count()` returns 2+ | Return match count, LLM adds more surrounding context |
| Diff verification fail | Hunk outside anchor span or threshold exceeded | Don't write file, return diff and reason |
| File not found | `FileNotFoundError` on read | Return error string |

The edit engine never raises exceptions to the caller — all errors are returned as `EditResult` with `success=False` and descriptive error fields.

### Test Coverage

The edit engine has 36 unit tests covering:
- Anchor matching (found once, not found, ambiguous)
- Diff verification (within span, outside span, threshold)
- Multi-edit atomicity (all succeed, one fails, reverse ordering)
- Edge cases (file not written on failure, git commit on success, whitespace normalization, large files, sequential edits)

10 additional tool-level integration tests verify the tools work correctly against real filesystems and git repos.

10 agent-level end-to-end evals verify the full system against a live LLM:
- Single-line edit, add function, create file, surgical edit
- Multi-file cross-file refactor, search-then-edit
- Error handling (missing function), context injection
- Large file edit (300+ lines), file precision (untouched files)

**Known eval gaps** (planned, not yet implemented — see `docs/evals/specs/04-06`):
- Large files (1000+ lines), edits near file boundaries, sequential edits with context drift
- Realistic TypeScript (React components, import graphs, generics, JSX)
- Anchor stress testing (near-duplicate functions, same code in different scopes, ambiguity resolution)

---

## Multi-Agent Design

*Not yet implemented — planned for Phase 5. Architecture designed and documented below.*

### Overview

The multi-agent system uses a **supervisor + worker** pattern with **file partitioning** to eliminate merge conflicts. Workers operate on disjoint file sets in parallel. Shared files are handled via deferred change requests applied by a merge agent after all workers complete.

### Supervisor Graph

The supervisor is a LangGraph `StateGraph` that orchestrates the full lifecycle:

```
decompose → dispatch → monitor → merge_gate → merge_agent → validate_project → report
                                                                    ↓
                                                               replan (on failure, up to 3×)
```

| Node | Purpose |
|------|---------|
| `decompose` | LLM breaks instruction into subtasks with explicit file ownership per worker. Decides `"parallel"` vs `"direct"` mode. |
| `dispatch` | Spawns worker subgraphs via `asyncio.gather()`. Passes `parent_run_id` for LangSmith trace nesting. |
| `monitor` | Polls worker heartbeats in shared state. Detects timeouts (default: 120s). |
| `merge_gate` | Collects worker results and pending `change_requests` from shared state. |
| `merge_agent` | LLM reads all change requests for each shared file, produces combined edits, applies via edit engine. |
| `validate_project` | Runs `tsc --noEmit` or equivalent project-wide check. |
| `report` | Summarizes results to user. |
| `replan` | On validation failure, reads errors, revises decomposition or dispatches fix-up tasks. Circuit breaker at 3 replans. |
| `execute_direct` | Simple task bypass — supervisor executes directly without spawning workers (single-file changes). |

**Supervisor state:**

```python
class SupervisorState(TypedDict):
    instruction: str
    subtasks: list[Subtask]
    worker_results: dict[str, WorkerResult]
    change_requests: list[ChangeRequest]
    validation_result: Optional[ValidationResult]
    replan_count: int  # circuit breaker
    max_replans: int   # default: 3
```

**Decomposition output:**

```json
{
  "mode": "parallel",
  "subtasks": [
    {"id": "auth-api", "instruction": "...", "files_owned": ["auth.ts"], "files_readable": ["types.ts"]},
    {"id": "auth-ui", "instruction": "...", "files_owned": ["LoginForm.tsx"], "files_readable": ["types.ts"]}
  ],
  "shared_files": ["types/index.ts", "package.json"]
}
```

Validation rules: no file appears in two workers' `files_owned`; all owned files exist; shared files excluded from all ownership.

### Worker Subgraphs

Each worker is a LangGraph `StateGraph` with its own ReAct loop:

| Node | Purpose | Transitions |
|------|---------|-------------|
| `plan` | Read assigned files, produce edit plan | → `execute` |
| `execute` | Call tools (read_file, edit_file, search_files, etc.) | → `validate` |
| `validate` | Check if edit succeeded | → `execute` (retry, max 3), → `complete`, → `failed` |
| `complete` | Report results to shared state | → END |
| `failed` | Report failure, circuit breaker triggered | → END |

**Worker state:**

```python
class WorkerState(TypedDict):
    subtask: Subtask
    files_owned: list[str]
    files_readable: list[str]
    edit_plan: list[PlannedEdit]
    edits_completed: int
    retry_count: int    # per current edit target, max 3
```

### File Ownership Enforcement

Enforced at the tool layer via `ToolRegistry`. When `files_owned` is set:
- `edit_file` on a non-owned file → returns error string: `"✗ Ownership error: {file} is not owned by this worker. Use request_shared_edit instead."`
- `create_file` on a non-owned path → same error
- `read_file` works on any file (workers need to read context)
- This is already implemented and tested (E-2.7)

### Shared Orchestrator State

In-memory Python object shared between supervisor and workers. Safe with async Python (cooperative yielding, no preemptive threads):

```python
class OrchestratorState:
    worker_status: dict[str, WorkerStatus]    # worker_id → phase, current_file, edits_completed, last_update
    change_requests: list[ChangeRequest]       # deferred shared file edits from workers
    worker_results: dict[str, WorkerResult]    # worker_id → diffs produced, files modified, validation status
```

**Worker heartbeat:** After each major step, workers update `worker_status` with their current phase, file, and timestamp. The supervisor's `monitor` node checks `last_update` against the timeout threshold.

### Shared File Handling

Workers cannot edit shared files directly. Instead:
1. Worker calls `request_shared_edit(file_path, description, old_content, new_content)`
2. This adds a `ChangeRequest` to `orchestrator_state.change_requests` — the file is NOT modified
3. After all workers complete, the merge agent collects all requests grouped by file
4. For each shared file, the merge agent LLM reads current contents + all change requests, produces combined edits
5. Combined edits applied via the edit engine with diff verification

### Communication Flow

```
Supervisor                    Worker A              Worker B
    │                            │                     │
    ├── decompose ──────────────►│                     │
    ├── dispatch (gather) ──────►├── plan              │
    │                            ├── execute           ├── plan
    │                            ├── validate          ├── execute
    │                            ├── complete ────────►│  ├── validate
    │  ◄── results ──────────────┘                     ├── complete
    │  ◄── results ────────────────────────────────────┘
    ├── merge_gate
    ├── merge_agent (shared files)
    ├── validate_project (tsc --noEmit)
    └── report
```

---

## Architecture Decisions

| Decision | Alternatives Considered | Chosen | Rationale |
|----------|------------------------|--------|-----------|
| **Agent framework** | Custom async loop, AutoGen, CrewAI | LangGraph (Python) | Mature state machine semantics with explicit node/edge control. Automatic LangSmith tracing without extra instrumentation. Built-in `ToolNode` and `add_messages` reducer handle the ReAct pattern cleanly. The library authors themselves recommend manual implementation over their higher-level `langgraph-supervisor` abstraction — we need fine-grained control over context engineering. |
| **File editing** | AST-based (ts-morph), unified diff as input, line-range replacement | Anchor-based (`old_content` → `new_content`) with unified diff verification | AST editing is language-specific and too complex for a one-week sprint. LLMs are unreliable at producing correctly formatted unified diffs (malformed `@@` headers, wrong context lines). Line-range replacement is fragile — line numbers drift after any edit. Anchor-based forces the LLM to state what it thinks exists in the file, catching stale context immediately. No line number dependency. The unified diff is generated *after* replacement as a verification layer, not as the edit mechanism. |
| **Server architecture** | REPL/CLI loop, WebSocket server | FastAPI + thin CLI client | Persistent process stays alive between instructions — no cold start per task. SSE streaming gives real-time progress. Separates the agent runtime from the user interface. Supports future multi-agent communication via HTTP endpoints. The CLI is a thin `click` + `httpx` wrapper — the server does all the work. |
| **Multi-agent conflict prevention** | Optimistic locking, file-level locks, merge resolution after conflict | File partitioning (disjoint ownership) | True file conflicts cannot occur when workers own disjoint file sets. Semantic conflicts (API shape mismatches between files) are caught by the project-wide typecheck after all workers finish. Simpler than lock-based approaches and eliminates an entire class of merge failures. Shared files handled separately via deferred change requests + merge agent. |
| **Session storage** | SQLite, PostgreSQL, in-memory | JSONL append-only files | Crash-safe by design (append-only, no transactions to corrupt). Human-readable with `cat`. Doubles as the rebuild log for deliverables. One file per session in `/.shipyard/sessions/`. SQLite deferred to post-MVP if cross-session query needs arise (can be rebuilt from JSONL). |
| **Observability** | Custom logging, OpenTelemetry, Weights & Biases | LangSmith | Automatic tracing from LangGraph — every node, LLM call, and tool invocation captured without extra code. Shareable trace links for submission. `@traceable` decorator available for manual nesting when needed (e.g., worker subgraphs). Environment variable activation (`LANGCHAIN_TRACING_V2=true`) means tracing can be toggled without code changes. |
| **LLM provider** | OpenRouter (model-agnostic proxy), direct Anthropic SDK | OpenAI API directly | Company-provided API keys. `ChatOpenAI` from `langchain-openai` provides native tool-calling support, streaming, and token counting. Model swappable via `SHIPYARD_MODEL_NAME` env var (gpt-4o, gpt-4.1-mini, etc.) without code changes. |
| **Whitespace handling** | Trust LLM output as-is, post-process all files | Detect-and-normalize per edit | LLMs frequently add/drop trailing spaces, change indentation style, or mix line endings. The normalize module detects the file's conventions (tabs vs spaces, indent size, `\n` vs `\r\n`) and converts `new_content` to match before applying. Conservative — only converts on clear mismatch. Trailing whitespace stripped unconditionally. |

---

## Trace Links

### Trace 1: Normal Run (single-file edit)

**Instruction:** "Change the add function in src/utils.ts to subtract instead of add"

**Tool call sequence:** `list_files` → `read_file` → `edit_file` → done

**Trace:** https://smith.langchain.com/public/4c370744-b3ab-482c-8da4-2afc2b1211e6/r

Shows the full ReAct cycle: agent reasons about the task, reads the file to get current contents, produces an `edit_file` call with correct `old_content`/`new_content`, edit engine applies the change, diff is verified, git commit is created.

### Trace 2: Error/Discovery Path (function not found)

**Instruction:** "Update the function processPayment in src/app.ts to add logging"

**Tool call sequence:** `search_files` → `search_files` → `list_files` → `read_file` → done (no edit — function doesn't exist)

**Trace:** https://smith.langchain.com/public/677b942b-5bf5-4d4e-9178-df8bf27aa8cd/r

Shows the agent's error handling: searches for `processPayment`, can't find it, reads the file to confirm, correctly concludes the function doesn't exist and reports back without making any changes. Demonstrates that the agent doesn't blindly edit when the target is missing.

---

## Ship Rebuild Log

*Placeholder — to be populated during the Ship app rebuild phase. Will document every instruction sent to the agent, every human intervention, and every failure/recovery.*

---

## Comparative Analysis

*Placeholder — to be populated after the Ship rebuild. Will cover:*
1. *What the agent built correctly without intervention*
2. *Where human intervention was needed and why*
3. *Comparison with manual development (speed, quality, cost)*
4. *Agent limitations discovered during the rebuild*
5. *Edit engine reliability metrics (retry rates, anchor accuracy)*
6. *Token economics (cost per feature, cost per edit)*
7. *Recommendations for production coding agents*

---

## Cost Analysis

*Placeholder — to be populated from session JSONL logs. Will include:*
- *Total tokens (input + output) across all sessions*
- *Cost per eval run*
- *Cost per feature during Ship rebuild*
- *Model comparison if multiple models tested*
- *Token efficiency metrics (tokens per successful edit)*
