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
