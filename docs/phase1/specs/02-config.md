# Spec 02: Configuration Module

## Objective
Create `shipyard/config.py` — a single source of truth for all configuration. Loads from environment variables with sensible defaults. Uses Pydantic `BaseSettings` for validation.

## Dependencies
- Spec 01 (project scaffolding) must be complete

## File: `shipyard/config.py`

### Design

Use `pydantic-settings` (included with Pydantic v2) for env var loading with type validation and defaults.

```python
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class ShipyardConfig(BaseSettings):
    """Central configuration for the Shipyard agent."""

    model_config = {"env_prefix": "SHIPYARD_"}

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # LLM (OpenRouter)
    openrouter_api_key: str = ""
    model_name: str = "anthropic/claude-sonnet-4-20250514"
    model_context_window: int = 200_000
    response_headroom_pct: float = 0.20  # reserve 20% for response

    # Project paths
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    shipyard_dir: str = ".shipyard"

    # Edit engine
    max_changed_lines: int = 100  # diff verification threshold
    max_edit_retries: int = 3

    # Multi-agent
    worker_timeout_seconds: int = 120
    max_replans: int = 3

    # Session
    session_dir: str = "sessions"
    notes_dir: str = "notes"
    max_notes: int = 20
    max_note_tokens: int = 2000

    # LangSmith
    langsmith_api_key: str = ""
    langsmith_project: str = "shipyard"
    langsmith_tracing: bool = False

    @property
    def shipyard_path(self) -> Path:
        """Absolute path to .shipyard directory."""
        return self.project_root / self.shipyard_dir

    @property
    def sessions_path(self) -> Path:
        return self.shipyard_path / self.session_dir

    @property
    def notes_path(self) -> Path:
        return self.shipyard_path / self.notes_dir


def get_config() -> ShipyardConfig:
    """Load config from environment. Call once at startup, pass the instance around."""
    return ShipyardConfig()
```

### Environment Variables

All prefixed with `SHIPYARD_`. Examples:
```bash
SHIPYARD_OPENROUTER_API_KEY=sk-or-...
SHIPYARD_MODEL_NAME=anthropic/claude-sonnet-4-20250514
SHIPYARD_PROJECT_ROOT=/path/to/target/project
SHIPYARD_PORT=8000
SHIPYARD_LANGSMITH_API_KEY=ls-...
SHIPYARD_LANGSMITH_TRACING=true
```

### Additional Dependency

Add `pydantic-settings>=2.0.0` to the `dependencies` list in `pyproject.toml` if not already present.

## Acceptance Criteria
- [ ] `from shipyard.config import get_config, ShipyardConfig` works
- [ ] `get_config()` returns a valid config with defaults when no env vars set
- [ ] Setting `SHIPYARD_PORT=9000` changes `config.port` to `9000`
- [ ] `config.shipyard_path` returns `project_root / ".shipyard"`
- [ ] `config.sessions_path` and `config.notes_path` are correct derived paths
- [ ] Invalid types (e.g., `SHIPYARD_PORT=abc`) raise a validation error
