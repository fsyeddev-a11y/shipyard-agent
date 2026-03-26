"""Tests for usage tracking (Spec 07)."""

import json
from pathlib import Path

import pytest

from shipyard.config import ShipyardConfig
from shipyard.session.usage import (
    SessionUsage,
    ModelUsage,
    UsageReport,
    calculate_usage,
)


def _make_config(tmp_path: Path) -> ShipyardConfig:
    """Create a config pointing at tmp_path as project root."""
    return ShipyardConfig(
        project_root=tmp_path,
        openai_api_key="test-key",
        cost_per_million_input=2.50,
        cost_per_million_output=10.00,
    )


def _write_session(sessions_dir: Path, session_id: str, events: list[dict]):
    """Write a JSONL session file."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    filepath = sessions_dir / f"{session_id}.jsonl"
    with filepath.open("w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def _llm_event(model: str = "gpt-4o", input_tokens: int = 1000, output_tokens: int = 200) -> dict:
    return {
        "type": "llm_call",
        "model": model,
        "tokens": {"input": input_tokens, "output": output_tokens, "cache_read": 0},
        "cost": 0.0,
        "duration_ms": 500,
        "timestamp": "2026-03-26T10:00:00Z",
    }


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------


def test_usage_empty(tmp_path):
    """No sessions → zeros."""
    config = _make_config(tmp_path)
    report = calculate_usage(config)
    assert report.total_input_tokens == 0
    assert report.total_output_tokens == 0
    assert report.total_cost == 0.0
    assert report.session_count == 0
    assert report.llm_call_count == 0
    assert report.by_session == []
    assert report.by_model == []


def test_usage_single_session(tmp_path):
    """Single session with 3 llm_call events."""
    config = _make_config(tmp_path)
    events = [
        _llm_event(input_tokens=1000, output_tokens=200),
        _llm_event(input_tokens=2000, output_tokens=300),
        _llm_event(input_tokens=500, output_tokens=100),
        {"type": "instruction", "content": "do something"},  # non-llm event
    ]
    _write_session(config.sessions_path, "sess-001", events)

    report = calculate_usage(config)
    assert report.session_count == 1
    assert report.llm_call_count == 3
    assert report.total_input_tokens == 3500
    assert report.total_output_tokens == 600
    assert len(report.by_session) == 1
    assert report.by_session[0].session_id == "sess-001"
    assert report.by_session[0].llm_calls == 3


def test_usage_multiple_sessions(tmp_path):
    """Two sessions — verify aggregation and per-session breakdown."""
    config = _make_config(tmp_path)
    _write_session(config.sessions_path, "sess-a", [
        _llm_event(input_tokens=1000, output_tokens=100),
        _llm_event(input_tokens=2000, output_tokens=200),
    ])
    _write_session(config.sessions_path, "sess-b", [
        _llm_event(input_tokens=3000, output_tokens=300),
    ])

    report = calculate_usage(config)
    assert report.session_count == 2
    assert report.llm_call_count == 3
    assert report.total_input_tokens == 6000
    assert report.total_output_tokens == 600

    ids = {s.session_id for s in report.by_session}
    assert ids == {"sess-a", "sess-b"}


def test_usage_per_model(tmp_path):
    """Mixed model calls — verify by_model grouping."""
    config = _make_config(tmp_path)
    _write_session(config.sessions_path, "sess-mix", [
        _llm_event(model="gpt-4o", input_tokens=1000, output_tokens=100),
        _llm_event(model="gpt-4.1-mini", input_tokens=2000, output_tokens=200),
        _llm_event(model="gpt-4o", input_tokens=3000, output_tokens=300),
    ])

    report = calculate_usage(config)
    models = {m.model: m for m in report.by_model}
    assert "gpt-4o" in models
    assert "gpt-4.1-mini" in models

    gpt4o = models["gpt-4o"]
    assert gpt4o.input_tokens == 4000
    assert gpt4o.output_tokens == 400
    assert gpt4o.call_count == 2

    mini = models["gpt-4.1-mini"]
    assert mini.input_tokens == 2000
    assert mini.output_tokens == 200
    assert mini.call_count == 1


def test_usage_cost_calculation(tmp_path):
    """Known token counts — verify cost matches formula."""
    config = _make_config(tmp_path)
    _write_session(config.sessions_path, "sess-cost", [
        _llm_event(input_tokens=1_000_000, output_tokens=100_000),
    ])

    report = calculate_usage(config)
    # cost = (1_000_000 * 2.50 + 100_000 * 10.00) / 1_000_000 = 2.50 + 1.00 = 3.50
    assert report.total_cost == pytest.approx(3.50)
    assert report.by_session[0].cost == pytest.approx(3.50)
    assert report.by_model[0].cost == pytest.approx(3.50)


@pytest.mark.asyncio
async def test_usage_endpoint(tmp_path):
    """GET /usage returns valid JSON matching UsageReport schema."""
    import httpx
    from httpx import ASGITransport
    from unittest.mock import patch

    config = _make_config(tmp_path)
    _write_session(config.sessions_path, "sess-ep", [
        _llm_event(input_tokens=5000, output_tokens=500),
    ])

    with patch("shipyard.server.app.get_config", return_value=config):
        from shipyard.server.app import app

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/usage")
            assert resp.status_code == 200
            data = resp.json()
            # Validate it parses as UsageReport
            report = UsageReport(**data)
            assert report.session_count == 1
            assert report.total_input_tokens == 5000
            assert report.total_output_tokens == 500


@pytest.mark.asyncio
async def test_usage_endpoint_session_filter(tmp_path):
    """GET /usage?session_id=X returns only that session."""
    import httpx
    from httpx import ASGITransport
    from unittest.mock import patch

    config = _make_config(tmp_path)
    _write_session(config.sessions_path, "sess-x", [
        _llm_event(input_tokens=1000, output_tokens=100),
    ])
    _write_session(config.sessions_path, "sess-y", [
        _llm_event(input_tokens=2000, output_tokens=200),
    ])

    with patch("shipyard.server.app.get_config", return_value=config):
        from shipyard.server.app import app

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/usage", params={"session_id": "sess-x"})
            assert resp.status_code == 200
            data = resp.json()
            report = UsageReport(**data)
            assert report.session_count == 1
            assert report.by_session[0].session_id == "sess-x"
            assert report.total_input_tokens == 1000


def test_usage_cli_offline(tmp_path):
    """Offline mode reads JSONL directly via calculate_usage."""
    config = _make_config(tmp_path)
    _write_session(config.sessions_path, "sess-offline", [
        _llm_event(input_tokens=4000, output_tokens=400),
        _llm_event(input_tokens=6000, output_tokens=600),
    ])

    report = calculate_usage(config)
    assert report.total_input_tokens == 10000
    assert report.total_output_tokens == 1000
    # cost = (10000 * 2.50 + 1000 * 10.00) / 1_000_000 = 0.025 + 0.01 = 0.035
    assert report.total_cost == pytest.approx(0.035)
    assert report.session_count == 1
    assert report.llm_call_count == 2
