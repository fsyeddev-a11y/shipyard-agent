# Phase 1: Foundation

## Goal
Stand up the skeleton project — FastAPI server, CLI client, config, git helpers, and project scaffolding. No agent logic yet. This is pure plumbing so that Phase 2 (edit engine) and beyond have a place to live.

## Specs
Each spec in `specs/` is a self-contained implementation document. They should be implemented in order:

| Order | Spec | What It Produces |
|-------|------|-----------------|
| 1 | `01-project-scaffolding.md` | `pyproject.toml`, directory structure, dependencies, `__init__.py` files |
| 2 | `02-config.md` | `shipyard/config.py` — env vars, paths, model config |
| 3 | `03-git-helpers.md` | `shipyard/edit_engine/git.py` — init, commit, revert |
| 4 | `04-fastapi-server.md` | `shipyard/server/app.py`, `shipyard/main.py` — routes, startup |
| 5 | `05-cli-client.md` | `shipyard/server/cli.py` — thin httpx client |

## Success Criteria
After Phase 1 is complete:
- `pip install -e .` works
- `shipyard-server` starts the FastAPI server on localhost:8000
- `shipyard "hello"` POSTs to the server and prints the echoed response
- `git init`, `git commit`, `git revert` helpers work in isolation
- All config loads from environment variables with sensible defaults

## Notes
- No agent logic, no LLM calls, no edit engine logic (that's Phase 2)
- The server endpoints are stubs — they accept input and echo it back
- The CLI streams the response via SSE
