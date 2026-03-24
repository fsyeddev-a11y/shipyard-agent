from langchain_openai import ChatOpenAI

from shipyard.config import ShipyardConfig


def get_llm(config: ShipyardConfig) -> ChatOpenAI:
    """
    Create and return a configured LLM client for OpenRouter.

    Uses ChatOpenAI with OpenRouter's base URL. This gives us:
    - OpenAI-compatible tool calling (function calling format)
    - Streaming support
    - Automatic token counting
    - Model flexibility (change model via config without code changes)

    Args:
        config: ShipyardConfig instance with openrouter_api_key and model_name

    Returns:
        A ChatOpenAI instance configured for OpenRouter
    """
    if not config.openrouter_api_key:
        raise ValueError(
            "SHIPYARD_OPENROUTER_API_KEY is not set. "
            "Set it in your environment: export SHIPYARD_OPENROUTER_API_KEY=sk-or-..."
        )

    return ChatOpenAI(
        model=config.model_name,
        openai_api_key=config.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_tokens=4096,
        model_kwargs={
            "extra_headers": {
                "HTTP-Referer": "https://shipyard.dev",
                "X-Title": "Shipyard Coding Agent",
            }
        },
    )
