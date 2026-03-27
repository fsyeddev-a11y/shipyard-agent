# Spec 07: Usage Tracking Endpoint + CLI Command

## Goal
Provide easy access to cumulative token usage and estimated cost across all sessions, without needing the OpenAI dashboard.

## What to Build

### 1. Usage calculator: `shipyard/session/usage.py`

**`calculate_usage(config) -> UsageReport`**

- Scans all `.shipyard/sessions/*.jsonl` files
- Extracts every `llm_call` event
- Aggregates: total_input_tokens, total_output_tokens, total_cost, session_count, llm_call_count
- Per-session breakdown: session_id, input_tokens, output_tokens, cost, llm_calls, duration
- Per-model breakdown: model_name, input_tokens, output_tokens, cost, call_count
- Cost estimation uses configurable pricing (default GPT-4o: $2.50/M input, $10.00/M output)

**Data models (Pydantic):**

```python
class SessionUsage(BaseModel):
    session_id: str
    input_tokens: int
    output_tokens: int
    cost: float
    llm_calls: int

class ModelUsage(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    call_count: int

class UsageReport(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    session_count: int
    llm_call_count: int
    by_session: list[SessionUsage]
    by_model: list[ModelUsage]
```

### 2. Server endpoint: `GET /usage`

- Returns `UsageReport` as JSON
- Optional query param `?session_id=xxx` to filter to one session

### 3. CLI command: `shipyard usage`

- Calls `GET /usage` and prints a formatted table:
```
Shipyard Usage Report
─────────────────────────────────────
Sessions: 12    LLM calls: 47

Model          Input      Output     Cost
gpt-4o         125,400    18,200     $0.50

Total tokens: 143,600    Est. cost: $0.50
─────────────────────────────────────
```
- `shipyard usage --detail` shows per-session breakdown
- `shipyard usage --offline` reads JSONL directly (no server needed)

### 4. Pricing config

Add to `ShipyardConfig`:
```python
cost_per_million_input: float = 2.50    # USD per 1M input tokens
cost_per_million_output: float = 10.00  # USD per 1M output tokens
```

These can be overridden via env vars `SHIPYARD_COST_PER_MILLION_INPUT` and `SHIPYARD_COST_PER_MILLION_OUTPUT` when using different models.

## Tests: `tests/test_usage.py`

- `test_usage_empty` — no sessions, returns zeros
- `test_usage_single_session` — create session with 3 llm_call events, verify totals
- `test_usage_multiple_sessions` — 2 sessions, verify aggregation and per-session breakdown
- `test_usage_per_model` — mixed model calls (gpt-4o + gpt-4.1-mini), verify by_model grouping
- `test_usage_cost_calculation` — known token counts, verify cost matches expected (2.50/M * input + 10.00/M * output)
- `test_usage_endpoint` — use FastAPI TestClient, hit GET /usage, verify JSON schema
- `test_usage_endpoint_session_filter` — filter by session_id, verify only that session returned
- `test_usage_cli_offline` — call the offline calculator directly, verify output

All tests use tmp_path with fake JSONL session files. No LLM calls needed.
