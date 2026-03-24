from langchain_openai import ChatOpenAI

from shipyard.config import ShipyardConfig


def get_llm(config: ShipyardConfig) -> ChatOpenAI:
    """
    Create and return a configured LLM client for OpenAI.

    Model is swappable via SHIPYARD_MODEL_NAME env var.
    Examples: gpt-4o, gpt-4.1-mini, o3, etc.

    Args:
        config: ShipyardConfig instance with openai_api_key and model_name

    Returns:
        A ChatOpenAI instance
    """
    if not config.openai_api_key:
        raise ValueError(
            "SHIPYARD_OPENAI_API_KEY is not set. "
            "Set it in your environment: export SHIPYARD_OPENAI_API_KEY=sk-..."
        )

    return ChatOpenAI(
        model=config.model_name,
        api_key=config.openai_api_key,
        temperature=0,
        max_tokens=4096,
    )
