from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class ShipyardConfig(BaseSettings):
    """Central configuration for the Shipyard agent."""

    model_config = {"env_prefix": "SHIPYARD_", "env_file": ".env", "env_file_encoding": "utf-8"}

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # LLM (OpenAI)
    openai_api_key: str = ""
    model_name: str = "gpt-4o"
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

    # Pricing
    cost_per_million_input: float = 2.50    # USD per 1M input tokens
    cost_per_million_output: float = 10.00  # USD per 1M output tokens

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
