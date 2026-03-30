"""
Tests for multi-agent coordination: state, worker, merge agent, orchestrator.

These tests validate the multi-agent architecture without requiring LLM calls.
They test state management, change requests, orchestrator lifecycle, and
file ownership enforcement.
"""

import asyncio
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from shipyard.agent.state import (
    OrchestratorState,
    WorkerStatus,
    WorkerPhase,
    WorkerResult,
    ChangeRequest,
    Subtask,
    DecompositionResult,
    TaskMode,
    PlannedEdit,
)


# --- OrchestratorState Tests ---

class TestOrchestratorState:
    def test_register_worker(self):
        state = OrchestratorState()
        state.register_worker("worker-1")
        assert "worker-1" in state.worker_status
        assert state.worker_status["worker-1"].phase == WorkerPhase.PLANNING

    def test_update_heartbeat(self):
        state = OrchestratorState()
        state.register_worker("worker-1")
        state.update_heartbeat(
            "worker-1",
            WorkerPhase.EXECUTING,
            current_file="test.ts",
            edits_completed=2,
            edits_planned=5,
        )
        status = state.worker_status["worker-1"]
        assert status.phase == WorkerPhase.EXECUTING
        assert status.current_file == "test.ts"
        assert status.edits_completed == 2
        assert status.edits_planned == 5

    def test_update_heartbeat_auto_registers(self):
        state = OrchestratorState()
        state.update_heartbeat("worker-new", WorkerPhase.EXECUTING)
        assert "worker-new" in state.worker_status

    def test_add_change_request(self):
        state = OrchestratorState()
        cr = ChangeRequest(
            worker_id="worker-1",
            file_path="shared/types.ts",
            description="Add User type",
            old_content="export {};",
            new_content="export interface User { id: string; }",
        )
        state.add_change_request(cr)
        assert len(state.change_requests) == 1
        assert state.change_requests[0].file_path == "shared/types.ts"

    def test_set_worker_result(self):
        state = OrchestratorState()
        result = WorkerResult(
            worker_id="worker-1",
            success=True,
            files_modified=["src/auth.ts"],
            diffs=["--- a/src/auth.ts\n+++ b/src/auth.ts"],
        )
        state.set_worker_result(result)
        assert "worker-1" in state.worker_results
        assert state.worker_results["worker-1"].success is True

    def test_all_workers_done_true(self):
        state = OrchestratorState()
        state.register_worker("w1")
        state.register_worker("w2")
        state.update_heartbeat("w1", WorkerPhase.COMPLETE)
        state.update_heartbeat("w2", WorkerPhase.FAILED)
        assert state.all_workers_done() is True

    def test_all_workers_done_false(self):
        state = OrchestratorState()
        state.register_worker("w1")
        state.register_worker("w2")
        state.update_heartbeat("w1", WorkerPhase.COMPLETE)
        state.update_heartbeat("w2", WorkerPhase.EXECUTING)
        assert state.all_workers_done() is False

    def test_timed_out_workers(self):
        state = OrchestratorState()
        state.register_worker("w1")
        state.register_worker("w2")
        # Simulate w1 being stale
        state.worker_status["w1"].last_update = time.time() - 200
        state.worker_status["w2"].last_update = time.time()
        timed_out = state.get_timed_out_workers(timeout_seconds=120)
        assert "w1" in timed_out
        assert "w2" not in timed_out

    def test_timed_out_ignores_completed(self):
        state = OrchestratorState()
        state.register_worker("w1")
        state.worker_status["w1"].last_update = time.time() - 200
        state.worker_status["w1"].phase = WorkerPhase.COMPLETE
        timed_out = state.get_timed_out_workers(timeout_seconds=120)
        assert len(timed_out) == 0


# --- State Model Tests ---

class TestStateModels:
    def test_subtask_creation(self):
        st = Subtask(
            id="auth-api",
            instruction="Implement auth routes",
            files_owned=["src/auth.ts", "src/middleware.ts"],
            files_readable=["src/types.ts"],
        )
        assert st.id == "auth-api"
        assert len(st.files_owned) == 2

    def test_decomposition_result_direct(self):
        result = DecompositionResult(
            mode=TaskMode.DIRECT,
            reasoning="Simple single-file change",
        )
        assert result.mode == TaskMode.DIRECT
        assert len(result.subtasks) == 0

    def test_decomposition_result_parallel(self):
        result = DecompositionResult(
            mode=TaskMode.PARALLEL,
            subtasks=[
                Subtask(id="t1", instruction="Do X", files_owned=["a.ts"], files_readable=[]),
                Subtask(id="t2", instruction="Do Y", files_owned=["b.ts"], files_readable=[]),
            ],
            shared_files=["shared.ts"],
            reasoning="Two independent file groups",
        )
        assert result.mode == TaskMode.PARALLEL
        assert len(result.subtasks) == 2
        assert "shared.ts" in result.shared_files

    def test_change_request_model(self):
        cr = ChangeRequest(
            worker_id="w1",
            file_path="types.ts",
            description="Add type",
            old_content="export {};",
            new_content="export type Foo = string;",
        )
        assert cr.worker_id == "w1"

    def test_worker_result_success(self):
        result = WorkerResult(
            worker_id="w1",
            success=True,
            files_modified=["a.ts", "b.ts"],
        )
        assert result.success is True
        assert result.error is None

    def test_worker_result_failure(self):
        result = WorkerResult(
            worker_id="w2",
            success=False,
            error="Anchor not found in auth.ts",
        )
        assert result.success is False
        assert "Anchor" in result.error


# --- Merge Agent Tests ---

class TestMergeHelpers:
    def test_has_conflicts_no_overlap(self):
        from shipyard.agent.merge_agent import _has_conflicts
        requests = [
            ChangeRequest(worker_id="w1", file_path="f.ts",
                         description="a", old_content="const x = 1;", new_content="const x = 2;"),
            ChangeRequest(worker_id="w2", file_path="f.ts",
                         description="b", old_content="const y = 1;", new_content="const y = 2;"),
        ]
        assert _has_conflicts(requests) is False

    def test_has_conflicts_overlapping(self):
        from shipyard.agent.merge_agent import _has_conflicts
        requests = [
            ChangeRequest(worker_id="w1", file_path="f.ts",
                         description="a", old_content="const x = 1;\nconst y = 2;",
                         new_content="const x = 10;\nconst y = 2;"),
            ChangeRequest(worker_id="w2", file_path="f.ts",
                         description="b", old_content="const y = 2;",
                         new_content="const y = 20;"),
        ]
        assert _has_conflicts(requests) is True

    def test_parse_edit_blocks(self):
        from shipyard.agent.merge_agent import _parse_edit_blocks
        text = """EDIT 1:
OLD:
```
const x = 1;
```
NEW:
```
const x = 2;
```

EDIT 2:
OLD:
```
const y = 1;
```
NEW:
```
const y = 2;
```
"""
        edits = _parse_edit_blocks(text)
        assert len(edits) == 2
        assert edits[0] == ("const x = 1;", "const x = 2;")
        assert edits[1] == ("const y = 1;", "const y = 2;")

    def test_extract_code_block(self):
        from shipyard.agent.merge_agent import _extract_code_block
        text = '```\nconst x = 1;\n```'
        assert _extract_code_block(text) == "const x = 1;"

    def test_extract_code_block_with_lang(self):
        from shipyard.agent.merge_agent import _extract_code_block
        text = '```typescript\nconst x = 1;\n```'
        assert _extract_code_block(text) == "const x = 1;"


# --- Request Shared Edit Tool Tests ---

class TestRequestSharedEdit:
    @pytest.mark.asyncio
    async def test_no_orchestrator_state_returns_error(self):
        from shipyard.tools.request_shared_edit import request_shared_edit
        result = await request_shared_edit(
            file_path="types.ts",
            description="Add type",
            old_content="old",
            new_content="new",
        )
        assert "\u2717" in result
        assert "only available in worker mode" in result

    @pytest.mark.asyncio
    async def test_queues_change_request(self):
        from shipyard.tools.request_shared_edit import request_shared_edit
        orch = OrchestratorState()
        result = await request_shared_edit(
            file_path="types.ts",
            description="Add type",
            old_content="export {};",
            new_content="export type Foo = string;",
            _orchestrator_state=orch,
            _worker_id="w1",
        )
        assert "\u2713" in result
        assert len(orch.change_requests) == 1
        assert orch.change_requests[0].worker_id == "w1"
        assert orch.change_requests[0].file_path == "types.ts"


# --- Decomposition Tests ---

class TestDecomposition:
    @pytest.mark.asyncio
    async def test_decompose_fallback_on_parse_error(self):
        """If LLM returns invalid JSON, decompose falls back to direct mode."""
        from shipyard.agent.supervisor import decompose_task

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(content="not valid json")

        with patch("shipyard.agent.supervisor.get_llm", return_value=mock_llm), \
             patch("shipyard.tools.list_files.list_files", new_callable=AsyncMock, return_value="src/\n  app.ts"):
            from shipyard.config import ShipyardConfig
            config = ShipyardConfig(project_root=Path("/tmp/test"))
            result = await decompose_task("do something", config)
            assert result.mode == TaskMode.DIRECT

    @pytest.mark.asyncio
    async def test_decompose_parses_parallel(self):
        """Decompose correctly parses a parallel mode response."""
        from shipyard.agent.supervisor import decompose_task

        mock_response = MagicMock(content=json.dumps({
            "mode": "parallel",
            "reasoning": "Two independent files",
            "subtasks": [
                {"id": "t1", "instruction": "Edit a.ts", "files_owned": ["a.ts"], "files_readable": []},
                {"id": "t2", "instruction": "Edit b.ts", "files_owned": ["b.ts"], "files_readable": []},
            ],
            "shared_files": ["types.ts"],
        }))
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_response

        with patch("shipyard.agent.supervisor.get_llm", return_value=mock_llm), \
             patch("shipyard.tools.list_files.list_files", new_callable=AsyncMock, return_value="src/"):
            from shipyard.config import ShipyardConfig
            config = ShipyardConfig(project_root=Path("/tmp/test"))
            result = await decompose_task("edit two files", config)
            assert result.mode == TaskMode.PARALLEL
            assert len(result.subtasks) == 2
            assert result.subtasks[0].id == "t1"
            assert "types.ts" in result.shared_files


# --- File Ownership Tests ---

class TestFileOwnership:
    @pytest.mark.asyncio
    async def test_ownership_blocks_edit(self, tmp_path):
        """ToolRegistry with files_owned blocks edits to non-owned files."""
        # Create a file
        test_file = tmp_path / "blocked.ts"
        test_file.write_text("const x = 1;")

        registry = ToolRegistry(
            project_root=tmp_path,
            files_owned=["allowed.ts"],
        )
        tools = registry.get_tools()

        # Find the edit_file tool
        edit_tool = None
        for t in tools:
            if t.name == "edit_file":
                edit_tool = t
                break
        assert edit_tool is not None

        # Try to edit a non-owned file
        result = await edit_tool.ainvoke({
            "file_path": "blocked.ts",
            "old_content": "const x = 1;",
            "new_content": "const x = 2;",
            "description": "change x",
        })
        assert "Ownership error" in str(result)

    @pytest.mark.asyncio
    async def test_ownership_allows_owned_file(self, tmp_path):
        """ToolRegistry with files_owned allows edits to owned files."""
        from shipyard.edit_engine.git import git_init_if_needed

        test_file = tmp_path / "allowed.ts"
        test_file.write_text("const x = 1;")
        git_init_if_needed(tmp_path)

        registry = ToolRegistry(
            project_root=tmp_path,
            files_owned=["allowed.ts"],
        )
        tools = registry.get_tools()

        edit_tool = None
        for t in tools:
            if t.name == "edit_file":
                edit_tool = t
                break

        result = await edit_tool.ainvoke({
            "file_path": "allowed.ts",
            "old_content": "const x = 1;",
            "new_content": "const x = 2;",
            "description": "change x",
        })
        assert "\u2713" in str(result) or "success" in str(result).lower()


import json
from shipyard.tools.registry import ToolRegistry
