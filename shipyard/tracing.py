import os
from shipyard.config import ShipyardConfig


def setup_langsmith(config: ShipyardConfig) -> bool:
    """
    Configure LangSmith tracing by setting environment variables.

    LangGraph reads these standard env vars directly — we bridge
    from our SHIPYARD_ prefixed config to the standard names.

    Call this once at server startup, before any LangGraph operations.

    Returns True if tracing is enabled, False otherwise.
    """
    if not config.langsmith_tracing or not config.langsmith_api_key:
        # Ensure tracing is disabled
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = config.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = config.langsmith_project

    return True


def get_trace_url(run_id: str, config: ShipyardConfig) -> str:
    """
    Construct a shareable LangSmith trace URL.

    Format: https://smith.langchain.com/public/{run_id}/r
    """
    return f"https://smith.langchain.com/public/{run_id}/r"


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is currently active."""
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
