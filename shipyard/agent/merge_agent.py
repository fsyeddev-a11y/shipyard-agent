"""
Merge agent — applies deferred shared file edits after workers complete.

When workers need to edit files they don't own, they submit ChangeRequests
via request_shared_edit. The merge agent:
1. Groups change requests by file
2. For each shared file, reads current contents
3. Uses the LLM to combine multiple change requests into coherent edits
4. Applies the combined edits via the edit engine (with diff verification)
"""

from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage

from shipyard.agent.llm import get_llm
from shipyard.agent.state import ChangeRequest, OrchestratorState
from shipyard.edit_engine.engine import apply_edit
from shipyard.config import ShipyardConfig


MERGE_SYSTEM_PROMPT = """You are a merge agent. Your job is to combine multiple change requests for a shared file into a single coherent set of edits.

Each change request specifies an old_content (text to find) and new_content (replacement).
Sometimes requests may conflict or overlap. Your job is to resolve conflicts and produce a final set of edits that satisfies all requests where possible.

Rules:
- Apply all non-conflicting changes
- For conflicting changes, prefer the edit with the clearer description or combine them
- Output your result as a series of EDIT blocks

Format your response as:
EDIT 1:
OLD:
```
exact old content
```
NEW:
```
exact new content
```

EDIT 2:
...

If all change requests can be applied independently (no conflicts), just confirm and I'll apply them directly.
Respond with DIRECT_APPLY if all edits are independent, or provide merged EDIT blocks if resolution is needed.
"""


async def run_merge_agent(
    config: ShipyardConfig,
    orchestrator_state: OrchestratorState,
) -> dict[str, list[str]]:
    """
    Process all pending change requests from workers.

    Groups requests by file, checks for conflicts, and either:
    - Applies edits directly (if no conflicts)
    - Uses LLM to merge conflicting edits

    Args:
        config: ShipyardConfig
        orchestrator_state: Contains change_requests from workers

    Returns:
        Dict mapping file_path -> list of result messages (success/error)
    """
    change_requests = orchestrator_state.change_requests
    if not change_requests:
        return {}

    # Group by file
    by_file: dict[str, list[ChangeRequest]] = {}
    for cr in change_requests:
        if cr.file_path not in by_file:
            by_file[cr.file_path] = []
        by_file[cr.file_path].append(cr)

    results: dict[str, list[str]] = {}

    for file_path, requests in by_file.items():
        results[file_path] = []

        if len(requests) == 1:
            # Single request — apply directly, no LLM needed
            cr = requests[0]
            result = await _apply_single_change(config, cr)
            results[file_path].append(result)
        else:
            # Multiple requests — check for conflicts
            if _has_conflicts(requests):
                # Use LLM to merge
                merged_results = await _merge_with_llm(config, file_path, requests)
                results[file_path].extend(merged_results)
            else:
                # No conflicts — apply each independently (bottom-to-top)
                sorted_requests = await _sort_by_position(config, file_path, requests)
                for cr in reversed(sorted_requests):
                    result = await _apply_single_change(config, cr)
                    results[file_path].append(result)

    return results


async def _apply_single_change(config: ShipyardConfig, cr: ChangeRequest) -> str:
    """Apply a single change request via the edit engine."""
    result = await apply_edit(
        file_path=cr.file_path,
        old_content=cr.old_content,
        new_content=cr.new_content,
        project_root=config.project_root,
        description=f"merge: {cr.description} (from worker {cr.worker_id})",
    )
    if result.success:
        return f"\u2713 Applied shared edit to {cr.file_path}: {cr.description}"
    else:
        return f"\u2717 Failed shared edit to {cr.file_path}: {result.error}"


def _has_conflicts(requests: list[ChangeRequest]) -> bool:
    """
    Check if multiple change requests for the same file conflict.

    Conflicts occur when:
    - Two requests target overlapping old_content
    - One request's new_content would break another's old_content anchor
    """
    for i, a in enumerate(requests):
        for b in requests[i + 1:]:
            # Check if old_content overlaps
            if a.old_content in b.old_content or b.old_content in a.old_content:
                return True
            # Check if new_content of one would affect old_content of another
            if a.old_content in b.new_content or b.old_content in a.new_content:
                return True
    return False


async def _sort_by_position(
    config: ShipyardConfig,
    file_path: str,
    requests: list[ChangeRequest],
) -> list[ChangeRequest]:
    """Sort change requests by their position in the file (top to bottom)."""
    full_path = Path(config.project_root) / file_path
    if not full_path.exists():
        return requests

    content = full_path.read_text(encoding="utf-8")
    def position(cr: ChangeRequest) -> int:
        idx = content.find(cr.old_content)
        return idx if idx >= 0 else len(content)

    return sorted(requests, key=position)


async def _merge_with_llm(
    config: ShipyardConfig,
    file_path: str,
    requests: list[ChangeRequest],
) -> list[str]:
    """
    Use the LLM to merge conflicting change requests.

    Reads the current file, sends all change requests to the LLM,
    and gets back a merged set of edits.
    """
    full_path = Path(config.project_root) / file_path
    if not full_path.exists():
        return [f"\u2717 File not found: {file_path}"]

    file_content = full_path.read_text(encoding="utf-8")

    # Build the merge prompt
    requests_text = ""
    for i, cr in enumerate(requests, 1):
        requests_text += f"\n### Request {i} (from worker {cr.worker_id})\n"
        requests_text += f"Description: {cr.description}\n"
        requests_text += f"Old content:\n```\n{cr.old_content}\n```\n"
        requests_text += f"New content:\n```\n{cr.new_content}\n```\n"

    user_msg = (
        f"File: {file_path}\n\n"
        f"Current file contents:\n```\n{file_content[:5000]}\n```\n\n"
        f"Change requests to merge:\n{requests_text}\n\n"
        "Merge these change requests. If they can all be applied independently, "
        "respond with DIRECT_APPLY. Otherwise, provide merged EDIT blocks."
    )

    llm = get_llm(config)
    messages = [
        SystemMessage(content=MERGE_SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    results = []

    if "DIRECT_APPLY" in response_text:
        # Apply each independently
        sorted_requests = await _sort_by_position(config, file_path, requests)
        for cr in reversed(sorted_requests):
            result = await _apply_single_change(config, cr)
            results.append(result)
    else:
        # Parse EDIT blocks from LLM response and apply
        edits = _parse_edit_blocks(response_text)
        for i, (old, new) in enumerate(edits):
            cr = ChangeRequest(
                worker_id="merge_agent",
                file_path=file_path,
                description=f"Merged edit {i+1}",
                old_content=old,
                new_content=new,
            )
            result = await _apply_single_change(config, cr)
            results.append(result)

    if not results:
        results.append(f"\u2717 Merge agent could not resolve changes for {file_path}")

    return results


def _parse_edit_blocks(response_text: str) -> list[tuple[str, str]]:
    """Parse EDIT blocks from LLM response into (old, new) pairs."""
    edits = []
    parts = response_text.split("EDIT ")

    for part in parts[1:]:  # Skip text before first EDIT
        old_content = ""
        new_content = ""

        # Extract OLD block
        if "OLD:" in part and "NEW:" in part:
            old_section = part.split("OLD:")[1].split("NEW:")[0]
            new_section = part.split("NEW:")[1]

            # Extract content between ``` markers
            old_content = _extract_code_block(old_section)
            new_content = _extract_code_block(new_section)

            if old_content and new_content:
                edits.append((old_content, new_content))

    return edits


def _extract_code_block(text: str) -> str:
    """Extract content between ``` markers."""
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            # Content is between first and second ```
            content = parts[1]
            # Strip optional language identifier on first line
            lines = content.split("\n", 1)
            if len(lines) > 1:
                return lines[1].rstrip("\n")
            return content.rstrip("\n")
        elif len(parts) >= 2:
            content = parts[1]
            lines = content.split("\n", 1)
            if len(lines) > 1:
                return lines[1].rstrip("\n")
            return content.rstrip("\n")
    return text.strip()
