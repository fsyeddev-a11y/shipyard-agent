# Spec 01: Project Scaffolding

## Objective
Create the full directory structure, `pyproject.toml`, and empty module files so the project is installable and importable.

## Directory Structure to Create

```
shipyard/
├── shipyard/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entrypoint (stub — created in spec 04)
│   ├── config.py                # Config module (stub — created in spec 02)
│   ├── server/
│   │   ├── __init__.py
│   │   ├── app.py               # FastAPI routes (stub — created in spec 04)
│   │   └── cli.py               # CLI client (stub — created in spec 05)
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── supervisor.py        # (empty stub for Phase 3+)
│   │   ├── worker.py            # (empty stub for Phase 3+)
│   │   ├── merge_agent.py       # (empty stub for Phase 5+)
│   │   └── state.py             # (empty stub for Phase 5+)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── read_file.py         # (empty stub for Phase 3)
│   │   ├── edit_file.py         # (empty stub for Phase 3)
│   │   ├── create_file.py       # (empty stub for Phase 3)
│   │   ├── list_files.py        # (empty stub for Phase 3)
│   │   ├── search_files.py      # (empty stub for Phase 3)
│   │   ├── run_command.py       # (empty stub for Phase 3)
│   │   ├── request_shared_edit.py  # (empty stub for Phase 5)
│   │   ├── notes.py             # (empty stub for Phase 6)
│   │   └── registry.py          # (empty stub for Phase 3)
│   ├── edit_engine/
│   │   ├── __init__.py
│   │   ├── engine.py            # (empty stub for Phase 2)
│   │   ├── diff.py              # (empty stub for Phase 2)
│   │   ├── normalize.py         # (empty stub for Phase 2)
│   │   └── git.py               # Git helpers (created in spec 03)
│   ├── context/
│   │   ├── __init__.py
│   │   ├── manager.py           # (empty stub for Phase 4)
│   │   ├── tiers.py             # (empty stub for Phase 4)
│   │   └── tokens.py            # (empty stub for Phase 4)
│   ├── session/
│   │   ├── __init__.py
│   │   ├── manager.py           # (empty stub for Phase 4)
│   │   ├── events.py            # (empty stub for Phase 4)
│   │   └── recovery.py          # (empty stub for Phase 4)
│   └── middleware/
│       ├── __init__.py
│       └── hooks.py             # (empty stub for Phase 4)
├── tests/
│   ├── __init__.py
│   ├── test_edit_engine.py      # (empty stub for Phase 2)
│   ├── test_tools.py            # (empty stub for Phase 3)
│   ├── test_supervisor.py       # (empty stub for Phase 3)
│   ├── test_worker.py           # (empty stub for Phase 5)
│   └── test_context_manager.py  # (empty stub for Phase 4)
├── pyproject.toml
├── .gitignore                   # (already exists)
└── README.md
```

## pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "shipyard"
version = "0.1.0"
description = "Autonomous coding agent with surgical file editing"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.27.0",
    "sse-starlette>=2.0.0",
    "pydantic>=2.0.0",
    "langgraph>=0.2.0",
    "langchain-openai>=0.2.0",
    "langsmith>=0.1.0",
    "tiktoken>=0.7.0",
    "click>=8.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.7.0",
]

[project.scripts]
shipyard = "shipyard.server.cli:main"
shipyard-server = "shipyard.main:run_server"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py311"
line-length = 100
```

## Stub File Content

All stub files (marked "empty stub for Phase X") should contain only:
```python
# Implemented in Phase X
```

The `__init__.py` files should be empty (zero bytes).

## README.md

Create a minimal README:

```markdown
# Shipyard

Autonomous coding agent with surgical file editing, multi-agent coordination, and persistent sessions.

## Setup

```bash
pip install -e ".[dev]"
```

## Usage

Start the server:
```bash
shipyard-server
```

Send an instruction:
```bash
shipyard "your instruction here"
```
```

## Acceptance Criteria
- [ ] All directories and files exist
- [ ] `pip install -e ".[dev]"` completes without errors
- [ ] `python -c "import shipyard"` works
- [ ] `python -c "from shipyard.edit_engine import git"` works (module importable)
- [ ] Stub files contain phase comments, not empty
