"""
request_shared_edit tool — allows workers to request edits to shared files.

Workers cannot directly edit files they don't own. Instead, they submit
a ChangeRequest that the merge agent processes after all workers complete.
"""

from pydantic import BaseModel, Field


class RequestSharedEditInput(BaseModel):
    """Input schema for request_shared_edit tool."""
    file_path: str = Field(description="Path to the shared file (relative to project root)")
    description: str = Field(description="What this edit does and why")
    old_content: str = Field(description="Exact text to find in the file")
    new_content: str = Field(description="Replacement text")


async def request_shared_edit(
    file_path: str,
    description: str,
    old_content: str,
    new_content: str,
    project_root=None,
    _orchestrator_state=None,
    _worker_id: str = "",
) -> str:
    """
    Queue a deferred edit to a shared file.

    This tool does NOT apply the edit immediately. Instead, it adds a
    ChangeRequest to the shared orchestrator state. The merge agent
    processes all change requests after workers complete.

    Args:
        file_path: Relative path to the shared file
        description: Human-readable description of the change
        old_content: Exact text to find (anchor)
        new_content: Replacement text
        project_root: Injected by ToolRegistry
        _orchestrator_state: Injected OrchestratorState
        _worker_id: Injected worker identifier

    Returns:
        Confirmation string
    """
    if _orchestrator_state is None:
        return (
            "\u2717 Error: request_shared_edit is only available in worker mode. "
            "In single-agent mode, edit the file directly with edit_file."
        )

    from shipyard.agent.state import ChangeRequest

    request = ChangeRequest(
        worker_id=_worker_id,
        file_path=file_path,
        description=description,
        old_content=old_content,
        new_content=new_content,
    )
    _orchestrator_state.add_change_request(request)

    return (
        f"\u2713 Shared edit queued for {file_path}: {description}\n"
        f"This will be applied by the merge agent after all workers complete."
    )
