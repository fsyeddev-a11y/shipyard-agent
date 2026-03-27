# Spec 03: LLM Client (OpenRouter)

## Objective
Create `shipyard/agent/llm.py` — a function that returns a configured LangChain chat model connected to OpenRouter. This is the LLM the agent loop uses for all reasoning and tool calls.

## Dependencies
- Spec 02 (tool registry) must be complete (for testing tool binding)
- Phase 1 config module must be available

## File: `shipyard/agent/llm.py`

### Design

OpenRouter exposes an OpenAI-compatible API. LangChain's `ChatOpenAI` class works directly with it by setting the `openai_api_base` to OpenRouter's endpoint.

```python
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
    return ChatOpenAI(
        model=config.model_name,
        openai_api_key=config.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0,          # deterministic for coding tasks
        max_tokens=4096,        # reasonable default for tool-calling responses
        model_kwargs={
            "extra_headers": {
                "HTTP-Referer": "https://shipyard.dev",  # OpenRouter requires this
                "X-Title": "Shipyard Coding Agent",
            }
        },
    )
```

### Implementation Notes

- `temperature=0` for deterministic, reproducible outputs on coding tasks
- `max_tokens=4096` is for the response only — input context is handled separately
- OpenRouter requires `HTTP-Referer` and optionally `X-Title` headers
- The model name comes from config (default: `anthropic/claude-sonnet-4-20250514`) — can be changed via `SHIPYARD_MODEL_NAME` env var
- No streaming configuration here — that's handled at the graph level when we invoke the agent
- This function is intentionally simple — it just creates the client. The agent loop (spec 04) handles tool binding and invocation.

### Validation

The function should raise a clear error if `openrouter_api_key` is empty:

```python
if not config.openrouter_api_key:
    raise ValueError(
        "SHIPYARD_OPENROUTER_API_KEY is not set. "
        "Set it in your environment: export SHIPYARD_OPENROUTER_API_KEY=sk-or-..."
    )
```

## Acceptance Criteria
- [ ] `from shipyard.agent.llm import get_llm` works
- [ ] `get_llm(config)` returns a `ChatOpenAI` instance
- [ ] Base URL is set to `https://openrouter.ai/api/v1`
- [ ] Model name comes from config
- [ ] Raises `ValueError` if API key is empty
- [ ] The returned model can have tools bound: `llm.bind_tools(tools)` (test with mock tools if no API key available)
