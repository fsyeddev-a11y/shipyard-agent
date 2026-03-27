# Spec 05: Middleware Hooks

## Objective
Create `shipyard/middleware/hooks.py` — deterministic hooks that run before/after each LLM call. These always execute regardless of LLM behavior. They handle session logging, token accounting, injection queue processing, and budget enforcement.

## Dependencies
- Spec 01 (session events) must be complete
- Spec 02 (session manager) must be complete
- Spec 04 (context manager) must be complete

## File: `shipyard/middleware/hooks.py`

### Design

```python
import time
from shipyard.session.manager import SessionManager
from shipyard.session.events import (
    LLMCallEvent, ToolCallEvent, ToolResultEvent,
    ContextEvictedEvent, ContextInjectedEvent, EditEvent,
)
from shipyard.context.manager import ContextManager
from shipyard.config import ShipyardConfig


class AgentMiddleware:
    """
    Deterministic middleware hooks for the agent loop.

    NOT agentic — these always execute regardless of LLM behavior.
    They provide logging, accounting, and injection processing.

    Usage:
        middleware = AgentMiddleware(session_manager, context_manager, config)

        # Before each LLM call:
        await middleware.before_llm_call()

        # After each LLM call:
        middleware.after_llm_call(response_metadata)

        # After each tool call:
        middleware.after_tool_call(tool_name, tool_args, tool_output)
    """

    def __init__(
        self,
        session_manager: SessionManager,
        context_manager: ContextManager,
        config: ShipyardConfig,
    ):
        self.session = session_manager
        self.context = context_manager
        self.config = config

        # Wire up eviction callback
        self.context.set_eviction_callback(self._on_eviction)

        # Track LLM call timing
        self._call_start_time: float = 0

    async def before_llm_call(self) -> None:
        """
        Runs before each LLM call.

        1. Process injection queue (check for /inject context)
        2. Enforce context budget (evict if needed)
        3. Log prompt metadata
        """
        # 1. Process injection queue
        injected_count = await self.context.process_injection_queue()
        if injected_count > 0:
            self.session.log_event(ContextInjectedEvent(
                source="human",
                label=f"{injected_count} item(s)",
                tier="tier2",
                token_count=self.context.tier2.token_count(),
            ))

        # 2. Enforce budget
        self.context.enforce_budget()

        # 3. Start timing
        self._call_start_time = time.time()

    def after_llm_call(
        self,
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> None:
        """
        Runs after each LLM call.

        1. Log LLM call event with token counts and timing
        2. Update token accounting
        """
        duration_ms = int((time.time() - self._call_start_time) * 1000)

        # Estimate cost (rough approximation — varies by model)
        # Using approximate rates: $3/M input, $15/M output for Claude Sonnet
        cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)

        self.session.log_event(LLMCallEvent(
            model=model or self.config.model_name,
            tokens={
                "input": input_tokens,
                "output": output_tokens,
                "cache_read": cache_read_tokens,
            },
            cost=cost,
            duration_ms=duration_ms,
        ))

    def after_tool_call(
        self,
        tool_name: str,
        tool_args: dict,
        tool_output: str,
        success: bool = True,
    ) -> None:
        """
        Runs after each tool execution.

        1. Log tool_call event
        2. Log tool_result event
        3. If it was an edit, log edit event
        """
        self.session.log_event(ToolCallEvent(
            tool=tool_name,
            args=tool_args,
        ))

        self.session.log_event(ToolResultEvent(
            tool=tool_name,
            output_summary=tool_output[:200],
            success=success,
        ))

        # Detect edit results and log edit event
        if tool_name in ("edit_file", "edit_file_multi") and success:
            file_path = tool_args.get("file_path", "")
            if "✓" in tool_output:
                self.session.log_event(EditEvent(
                    file_path=file_path,
                    diff_summary=_extract_diff_summary(tool_output),
                    commit_hash=_extract_commit_hash(tool_output),
                    validated=True,
                ))

    def _on_eviction(self, entry) -> None:
        """Called when Tier 3 content is evicted."""
        self.session.log_event(ContextEvictedEvent(
            content_summary=entry.content[:100] + "..." if len(entry.content) > 100 else entry.content,
            tier="tier3",
            tokens_freed=entry.tokens,
        ))


def _extract_diff_summary(output: str) -> str:
    """Extract '+N -M lines' from tool output."""
    for part in output.split():
        if part.startswith("+") and "-" in output:
            # Look for the pattern "+N -M lines"
            try:
                idx = output.index("+")
                end = output.index("lines", idx) + 5
                return output[idx:end]
            except ValueError:
                pass
    return ""


def _extract_commit_hash(output: str) -> str:
    """Extract commit hash from tool output like '(commit: abc1234)'."""
    if "commit:" in output:
        try:
            start = output.index("commit:") + 8
            end = output.index(")", start)
            return output[start:end].strip()
        except ValueError:
            pass
    return ""
```

### Implementation Notes

- The middleware is **not** a LangGraph node — it wraps the LLM call in the agent node
- `before_llm_call` is async because it processes the injection queue
- `after_llm_call` is sync because it just logs
- Cost estimation uses rough per-token rates — these can be refined later or pulled from OpenRouter's response headers
- Edit detection in `after_tool_call` looks for the "✓" success marker in tool output — this is fragile but sufficient for MVP
- The eviction callback logs to the session so evicted content is tracked

## Acceptance Criteria
- [ ] `AgentMiddleware` initializes with session manager, context manager, and config
- [ ] `before_llm_call()` processes injection queue and enforces budget
- [ ] `after_llm_call()` logs LLMCallEvent with tokens, cost, and duration
- [ ] `after_tool_call()` logs ToolCallEvent and ToolResultEvent
- [ ] Edit tool calls also produce EditEvent in the session log
- [ ] Eviction callback logs ContextEvictedEvent
- [ ] All events are written to the session JSONL via session manager
