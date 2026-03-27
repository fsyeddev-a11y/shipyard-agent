# Phase 4: Context Manager + Session Manager + Middleware

## Goal
Add the infrastructure that makes the agent production-ready: session logging (JSONL), context management (three-tier model with token budgets), token counting, middleware hooks (before/after each LLM call), and the injection endpoint. After this phase, every agent action is logged, context is managed within token budgets, and external context can be injected mid-execution.

## Specs

| Order | Spec | What It Produces |
|-------|------|-----------------|
| 1 | `01-session-events.md` | `shipyard/session/events.py` — Pydantic event models for JSONL logging |
| 2 | `02-session-manager.md` | `shipyard/session/manager.py` — session lifecycle, JSONL logging, list/resume/export |
| 3 | `03-token-counting.md` | `shipyard/context/tokens.py` — token counting via tiktoken |
| 4 | `04-context-manager.md` | `shipyard/context/manager.py` + `tiers.py` — three-tier context model with eviction |
| 5 | `05-middleware.md` | `shipyard/middleware/hooks.py` — before/after LLM call hooks, injection queue |
| 6 | `06-wire-phase4.md` | Wire session manager, context manager, and middleware into the agent loop + server |

## Dependencies
- Phase 3 complete (agent loop, tools, server)

## Success Criteria
- Every agent action logged to `/.shipyard/sessions/{session_id}.jsonl`
- `llm_call` events include token counts and timing
- Context stays within 80% of model context window
- Tier 3 eviction drops oldest content when budget is exceeded
- `/inject` endpoint pushes context into the agent's next turn
- `/session/list` returns real sessions
- Crash recovery detects interrupted tasks
