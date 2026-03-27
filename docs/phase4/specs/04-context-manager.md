# Spec 04: Context Manager

## Objective
Create `shipyard/context/manager.py` and `shipyard/context/tiers.py` — the three-tier context management system that assembles prompts for each LLM call, enforces token budgets, and performs non-destructive eviction.

## Dependencies
- Spec 03 (token counting) must be complete
- Phase 1 config must be available

## File: `shipyard/context/tiers.py`

### Design

```python
from dataclasses import dataclass, field
from shipyard.context.tokens import count_tokens


@dataclass
class Tier1Pinned:
    """
    Tier 1: Pinned context — always included, never evicted.

    Contains: system prompt, tool definitions, project identity,
    current task instruction, critical constraints.
    """
    items: list[str] = field(default_factory=list)

    def add(self, content: str) -> None:
        self.items.append(content)

    def get_content(self) -> str:
        return "\n\n".join(self.items)

    def token_count(self) -> int:
        return count_tokens(self.get_content())


@dataclass
class Tier2Container:
    """A single named container in Tier 2."""
    name: str
    content: str = ""
    max_tokens: int = 5000

    def update(self, content: str) -> None:
        self.content = content

    def clear(self) -> None:
        self.content = ""

    def token_count(self) -> int:
        return count_tokens(self.content)


class Tier2Containers:
    """
    Tier 2: Named containers — agent explicitly adds/removes.

    Standard containers:
    - "active_files": file paths + summaries being worked on
    - "edit_plan": current plan with step status
    - "errors": most recent errors (replaced, not appended)
    - "notes_index": one-line summaries of available notes
    """
    def __init__(self):
        self.containers: dict[str, Tier2Container] = {}

    def set(self, name: str, content: str, max_tokens: int = 5000) -> None:
        """Create or update a container."""
        if name in self.containers:
            self.containers[name].update(content)
        else:
            self.containers[name] = Tier2Container(name=name, content=content, max_tokens=max_tokens)

    def get(self, name: str) -> str:
        """Get a container's content."""
        c = self.containers.get(name)
        return c.content if c else ""

    def remove(self, name: str) -> None:
        """Remove a container."""
        self.containers.pop(name, None)

    def get_all_content(self) -> str:
        """Concatenate all non-empty containers."""
        parts = []
        for c in self.containers.values():
            if c.content:
                parts.append(f"[{c.name}]\n{c.content}")
        return "\n\n".join(parts)

    def token_count(self) -> int:
        return sum(c.token_count() for c in self.containers.values())


@dataclass
class Tier3Entry:
    """A single entry in the sliding window."""
    content: str
    role: str  # "user", "assistant", "tool"
    timestamp: str = ""
    tokens: int = 0
    evicted: bool = False


class Tier3Sliding:
    """
    Tier 3: Sliding window — recency-based eviction.

    Contains full file contents from reads, command output,
    conversation history turns.
    """
    def __init__(self, max_tokens: int = 80_000):
        self.entries: list[Tier3Entry] = []
        self.max_tokens = max_tokens

    def add(self, content: str, role: str = "assistant", timestamp: str = "") -> None:
        tokens = count_tokens(content)
        self.entries.append(Tier3Entry(
            content=content, role=role, timestamp=timestamp, tokens=tokens
        ))

    def evict_oldest(self, tokens_to_free: int) -> list[Tier3Entry]:
        """
        Evict oldest non-evicted entries until tokens_to_free is met.

        Non-destructive: entries are marked evicted=True but kept in the list
        for session logging.

        Returns list of evicted entries.
        """
        freed = 0
        evicted = []
        for entry in self.entries:
            if entry.evicted:
                continue
            if freed >= tokens_to_free:
                break
            entry.evicted = True
            freed += entry.tokens
            evicted.append(entry)
        return evicted

    def get_active_content(self) -> list[dict]:
        """Return non-evicted entries as message-format dicts."""
        return [
            {"role": e.role, "content": e.content}
            for e in self.entries if not e.evicted
        ]

    def token_count(self) -> int:
        return sum(e.tokens for e in self.entries if not e.evicted)

    def total_entries(self) -> int:
        return len([e for e in self.entries if not e.evicted])
```

## File: `shipyard/context/manager.py`

```python
from shipyard.context.tiers import Tier1Pinned, Tier2Containers, Tier3Sliding
from shipyard.context.tokens import count_tokens, estimate_budget
from shipyard.config import ShipyardConfig
from datetime import datetime, timezone
import asyncio


class ContextManager:
    """
    Assembles the prompt for each LLM call using the three-tier model.

    Tier 1 (Pinned): always present
    Tier 2 (Containers): agent-managed named blocks
    Tier 3 (Sliding): recency-based, auto-evicted when budget exceeded
    """

    def __init__(self, config: ShipyardConfig):
        self.config = config
        self.budget = estimate_budget(
            config.model_context_window,
            config.response_headroom_pct,
        )
        self.tier1 = Tier1Pinned()
        self.tier2 = Tier2Containers()
        self.tier3 = Tier3Sliding(max_tokens=self.budget["tier3_budget"])

        # Injection queue: external context pushed via /inject
        self._injection_queue: asyncio.Queue = asyncio.Queue()

        # Eviction callback for session logging
        self._on_eviction = None  # set by middleware

    def set_eviction_callback(self, callback):
        """Set a callback for when content is evicted (for session logging)."""
        self._on_eviction = callback

    def get_total_tokens(self) -> int:
        """Current total token usage across all tiers."""
        return (
            self.tier1.token_count()
            + self.tier2.token_count()
            + self.tier3.token_count()
        )

    def enforce_budget(self) -> list:
        """
        Check if total tokens exceed the eviction threshold.
        If so, evict oldest Tier 3 content until under budget.

        Returns list of evicted entries (for session logging).
        """
        total = self.get_total_tokens()
        threshold = self.budget["eviction_threshold"]

        if total <= threshold:
            return []

        tokens_to_free = total - self.budget["available"]
        evicted = self.tier3.evict_oldest(tokens_to_free)

        if self._on_eviction:
            for entry in evicted:
                self._on_eviction(entry)

        return evicted

    def assemble_messages(self) -> list[dict]:
        """
        Assemble the full message list for an LLM call.

        Order:
        1. Tier 1 pinned content (as system message)
        2. Tier 2 containers (as system message addendum)
        3. Tier 3 sliding window entries (as conversation messages)

        Enforces budget before assembling.
        """
        self.enforce_budget()

        messages = []

        # Tier 1: system message
        tier1_content = self.tier1.get_content()
        tier2_content = self.tier2.get_all_content()

        system_content = tier1_content
        if tier2_content:
            system_content += "\n\n---\n" + tier2_content

        if system_content:
            messages.append({"role": "system", "content": system_content})

        # Tier 3: conversation history
        messages.extend(self.tier3.get_active_content())

        return messages

    def inject_context(self, content: str, tier: str = "tier2", label: str = "") -> None:
        """
        Inject context directly (synchronous).

        Args:
            content: The context to inject
            tier: "tier1" or "tier2"
            label: Label for the context block (used as container name for tier2)
        """
        if tier == "tier1":
            self.tier1.add(content)
        elif tier == "tier2":
            name = label or f"injected_{datetime.now(timezone.utc).strftime('%H%M%S')}"
            self.tier2.set(name, content)

    async def queue_injection(self, content: str, tier: str = "tier2", label: str = "") -> None:
        """Queue context for injection (from /inject endpoint)."""
        await self._injection_queue.put({"content": content, "tier": tier, "label": label})

    async def process_injection_queue(self) -> int:
        """
        Process all pending injections from the queue.
        Called by middleware before each LLM call.

        Returns number of items processed.
        """
        count = 0
        while not self._injection_queue.empty():
            try:
                item = self._injection_queue.get_nowait()
                self.inject_context(
                    content=item["content"],
                    tier=item["tier"],
                    label=item.get("label", ""),
                )
                count += 1
            except asyncio.QueueEmpty:
                break
        return count
```

### Implementation Notes

- **Non-destructive eviction**: Tier 3 entries are marked `evicted=True` but remain in the list. The session log records what was evicted and when.
- **Injection queue**: The `/inject` endpoint pushes to an `asyncio.Queue`. The middleware calls `process_injection_queue()` before each LLM call.
- **Budget enforcement**: Called automatically in `assemble_messages()`. Also callable manually via `enforce_budget()`.
- **Message assembly order**: system (Tier 1 + Tier 2) → conversation (Tier 3). The LLM sees Tier 1 first, Tier 2 as additional system context, then the conversation.

## Acceptance Criteria
- [ ] `ContextManager(config)` initializes with correct budget breakdown
- [ ] `tier1.add()` adds pinned content that's always included
- [ ] `tier2.set()` / `tier2.remove()` manage named containers
- [ ] `tier3.add()` adds entries; `tier3.evict_oldest()` marks oldest as evicted
- [ ] `enforce_budget()` evicts Tier 3 content when over threshold
- [ ] Evicted entries are marked but not deleted (non-destructive)
- [ ] `assemble_messages()` returns properly ordered message list
- [ ] `inject_context()` adds to the correct tier
- [ ] `queue_injection()` / `process_injection_queue()` work with asyncio.Queue
- [ ] `get_total_tokens()` returns accurate token count across all tiers
