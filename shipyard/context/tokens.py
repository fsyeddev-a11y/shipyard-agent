import tiktoken


# Use cl100k_base as a reasonable approximation for most models
# (GPT-4, Claude via OpenRouter, etc.)
_DEFAULT_ENCODING = "cl100k_base"
_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    """Lazy-load the tiktoken encoder."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding(_DEFAULT_ENCODING)
    return _encoder


def count_tokens(text: str) -> int:
    """
    Count tokens in a text string.

    Uses cl100k_base encoding as a reasonable approximation.
    This is not exact for every model but is close enough for
    budget enforcement (within ~5-10%).
    """
    if not text:
        return 0
    encoder = _get_encoder()
    return len(encoder.encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    """
    Count tokens across a list of chat messages.

    Each message is a dict with "role" and "content" keys.
    Accounts for message overhead (~4 tokens per message for
    role/separator tokens).
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content)
        total += 4  # role + separator overhead per message
    total += 2  # reply priming
    return total


def estimate_budget(
    model_context_window: int,
    response_headroom_pct: float = 0.20,
) -> dict:
    """
    Calculate token budgets for the three-tier context model.

    Returns dict with: total, response_reserve, available,
    tier1_budget, tier2_budget, tier3_budget, eviction_threshold.
    """
    response_reserve = int(model_context_window * response_headroom_pct)
    available = model_context_window - response_reserve
    tier1_budget = min(10_000, available // 10)
    tier2_budget = min(30_000, available // 4)
    tier3_budget = available - tier1_budget - tier2_budget
    eviction_threshold = int(model_context_window * 0.80)

    return {
        "total": model_context_window,
        "response_reserve": response_reserve,
        "available": available,
        "tier1_budget": tier1_budget,
        "tier2_budget": tier2_budget,
        "tier3_budget": tier3_budget,
        "eviction_threshold": eviction_threshold,
    }


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """
    Truncate text to fit within a token budget.

    Truncates from the end. Adds "[...truncated]" marker if truncated.
    """
    if not text:
        return text
    encoder = _get_encoder()
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    # Leave room for truncation marker
    marker = "\n[...truncated]"
    marker_tokens = len(encoder.encode(marker))
    truncated_tokens = tokens[:max_tokens - marker_tokens]
    return encoder.decode(truncated_tokens) + marker
