import asyncio
from datetime import datetime, timezone

from shipyard.config import ShipyardConfig
from shipyard.context.tiers import Tier1Pinned, Tier2Containers, Tier3Sliding
from shipyard.context.tokens import estimate_budget


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
        self._on_eviction = None

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

        # Tier 1 + Tier 2: system message
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
