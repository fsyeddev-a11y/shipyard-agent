# Phase 3: Tools + Single Agent Loop

## Goal
Implement the tool suite the agent uses to interact with the codebase, wire up the LLM via OpenRouter, and build the single-agent loop (supervisor in "direct" mode). By the end of this phase, the agent can receive an instruction, reason about it, call tools, edit files, and return results — the first end-to-end agentic execution.

## Specs

| Order | Spec | What It Produces |
|-------|------|-----------------|
| 1 | `01-tools.md` | `shipyard/tools/` — read_file, edit_file, create_file, list_files, search_files, run_command |
| 2 | `02-tool-registry.md` | `shipyard/tools/registry.py` — tool registration, LangGraph-compatible tool definitions |
| 3 | `03-llm-client.md` | `shipyard/agent/llm.py` — OpenRouter LLM client via langchain-openai |
| 4 | `04-single-agent-loop.md` | `shipyard/agent/supervisor.py` — single-agent LangGraph graph (direct mode) |
| 5 | `05-wire-server.md` | Wire `/instruct` endpoint to the agent loop, SSE streaming of agent events |

## Dependencies
- Phase 1 (server, config, git helpers) complete
- Phase 2 (edit engine + tests) complete

## Success Criteria
After Phase 3 is complete:
- All 6 tools work independently and return structured output
- `shipyard-server` starts and accepts instructions
- Agent receives instruction → calls tools → edits files → git commits → returns result
- SSE stream shows agent progress (tool calls, results, completion)
- End-to-end test: `shipyard "read the file X and tell me what it contains"` works
