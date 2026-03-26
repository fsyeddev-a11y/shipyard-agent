"""Usage tracking: scan JSONL session logs and aggregate token/cost data."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from shipyard.config import ShipyardConfig


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


def _compute_cost(input_tokens: int, output_tokens: int, config: ShipyardConfig) -> float:
    return (
        input_tokens * config.cost_per_million_input
        + output_tokens * config.cost_per_million_output
    ) / 1_000_000


def calculate_usage(config: ShipyardConfig, session_id: str | None = None) -> UsageReport:
    """Scan .shipyard/sessions/*.jsonl and aggregate token usage and cost."""
    sessions_path = config.sessions_path

    if not sessions_path.exists():
        return UsageReport(
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost=0.0,
            session_count=0,
            llm_call_count=0,
            by_session=[],
            by_model=[],
        )

    jsonl_files = sorted(sessions_path.glob("*.jsonl"))

    # Filter to specific session if requested
    if session_id:
        jsonl_files = [f for f in jsonl_files if f.stem == session_id]

    # Per-session accumulators
    session_data: dict[str, dict] = {}
    # Per-model accumulators
    model_data: dict[str, dict] = {}

    for filepath in jsonl_files:
        sid = filepath.stem
        if sid not in session_data:
            session_data[sid] = {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0}

        for line in filepath.read_text().splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") != "llm_call":
                continue

            tokens = event.get("tokens", {})
            inp = tokens.get("input", 0)
            out = tokens.get("output", 0)

            session_data[sid]["input_tokens"] += inp
            session_data[sid]["output_tokens"] += out
            session_data[sid]["llm_calls"] += 1

            model_name = event.get("model", "unknown")
            if model_name not in model_data:
                model_data[model_name] = {"input_tokens": 0, "output_tokens": 0, "call_count": 0}
            model_data[model_name]["input_tokens"] += inp
            model_data[model_name]["output_tokens"] += out
            model_data[model_name]["call_count"] += 1

    # Build per-session list
    by_session = []
    for sid, data in session_data.items():
        cost = _compute_cost(data["input_tokens"], data["output_tokens"], config)
        by_session.append(SessionUsage(
            session_id=sid,
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            cost=cost,
            llm_calls=data["llm_calls"],
        ))

    # Build per-model list
    by_model = []
    for model_name, data in model_data.items():
        cost = _compute_cost(data["input_tokens"], data["output_tokens"], config)
        by_model.append(ModelUsage(
            model=model_name,
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            cost=cost,
            call_count=data["call_count"],
        ))

    total_input = sum(s.input_tokens for s in by_session)
    total_output = sum(s.output_tokens for s in by_session)
    total_cost = _compute_cost(total_input, total_output, config)

    return UsageReport(
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost=total_cost,
        session_count=len(by_session),
        llm_call_count=sum(s.llm_calls for s in by_session),
        by_session=by_session,
        by_model=by_model,
    )
