# Benchmarking Framework

## Goal
Build the benchmark runner, regression detection, and scorecard before any feature work. Establish a baseline from existing tests, then use it to gate every future change.

## Specs

| Order | Spec | What It Produces |
|-------|------|-----------------|
| 1 | `01-benchmark-runner.md` | `benchmarks/runner.py`, `benchmarks/regression.py`, `benchmarks/scorecard.py`, `benchmarks/__init__.py` |
| 2 | `02-wire-existing-tests.md` | `benchmarks/run.py` CLI entry point, wires Layer 0/1/2 to existing pytest tests, establishes baseline |
| 3 | `03-efficiency-metrics.md` | SPEC-07: adds EfficiencyMetrics to Layer 2+ evals, baseline measurement |

## Then
After baseline is established: implement SPEC-01 (auto-loading project context), run full benchmarks, confirm no regressions.
