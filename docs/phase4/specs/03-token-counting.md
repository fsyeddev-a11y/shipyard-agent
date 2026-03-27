# Spec 03: Token Counting

## Objective
Create `shipyard/context/tokens.py` — token counting utilities used by the context manager to enforce budget limits. Uses tiktoken for estimation.

## Dependencies
- Phase 1 complete (tiktoken in dependencies)

## File: `shipyard/context/tokens.py`

### Design

```python
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

    Args:
        text: The text to count tokens for

    Returns:
        Token count
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

    Args:
        messages: List of {"role": "...", "content": "..."} dicts

    Returns:
        Total token count including message overhead
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

    Args:
        model_context_window: Total context window size (e.g., 200000)
        response_headroom_pct: Fraction reserved for response (default 20%)

    Returns:
        Dict with budget breakdown:
        {
            "total": model_context_window,
            "response_reserve": int,
            "available": int,       # total - response_reserve
            "tier1_budget": int,    # ~10k fixed
            "tier2_budget": int,    # ~20-30k
            "tier3_budget": int,    # remainder
            "eviction_threshold": int,  # 80% of total — start evicting here
        }
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

    Args:
        text: Text to potentially truncate
        max_tokens: Maximum tokens allowed

    Returns:
        Original text if within budget, or truncated text with marker
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
```

### Implementation Notes

- `cl100k_base` is used for all models as an approximation — it's the tokenizer for GPT-4 and close enough for Claude/other models for budget enforcement purposes
- Lazy-load the encoder to avoid import-time overhead
- `count_messages_tokens` adds ~4 tokens per message for role/separator overhead (standard OpenAI accounting)
- `estimate_budget` calculates fixed budgets for Tier 1 and 2, with Tier 3 getting the remainder
- `truncate_to_tokens` is used for truncating tool output and conversation history

## Acceptance Criteria
- [ ] `count_tokens("hello world")` returns a reasonable count (2-3 tokens)
- [ ] `count_tokens("")` returns 0
- [ ] `count_messages_tokens` accounts for message overhead
- [ ] `estimate_budget(200_000)` returns budget with all fields, eviction_threshold at 160k
- [ ] `truncate_to_tokens("long text...", 5)` truncates and adds marker
- [ ] `truncate_to_tokens("short", 1000)` returns original text unchanged
