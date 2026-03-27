# Phase 6: LangSmith Tracing (MVP)

## Goal
Enable LangSmith tracing so every agent run is observable — every LLM call, tool invocation, and graph node is captured and viewable via shareable trace links. This completes the MVP.

## Specs

| Order | Spec | What It Produces |
|-------|------|-----------------|
| 1 | `01-langsmith-tracing.md` | Tracing setup, env var wiring, trace link extraction, run metadata |

## Why One Spec
LangGraph traces to LangSmith automatically when the env vars are set. The work is:
1. Set the env vars correctly at startup based on config
2. Add run metadata (session_id, instruction) to traces
3. Extract and return the trace link URL after each run
4. Verify with two demonstrable traces (normal + error path)

## Dependencies
- Phase 4 complete (agent loop, session manager)
- LangSmith account + API key

## Success Criteria
- Setting `SHIPYARD_LANGSMITH_TRACING=true` enables tracing
- Every agent run appears in LangSmith dashboard
- Trace shows: graph nodes, LLM calls with prompts/responses, tool calls with inputs/outputs
- Shareable trace link URL returned in the `done` SSE event
- Two trace links captured: one for a successful edit, one for an error/retry path
