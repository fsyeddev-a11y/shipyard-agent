# Evals: Test Suite for Shipyard

## Goal
Implement the evaluation suite defined in EVALS.md. Three layers: deterministic edit engine tests (done), tool integration tests, and agent-level end-to-end evals.

## Implemented Specs

| Order | Spec | Status |
|-------|------|--------|
| 1 | `01-layer2-tool-tests.md` | ✓ 10 passing, 1 skipped |
| 2 | `02-layer3-framework.md` | ✓ Framework + E-3.1 through E-3.4 |
| 3 | `03-layer3-remaining.md` | ✓ E-3.5 through E-3.10 |

## Planned Specs (Incomplete — Need Further Planning)

| Spec | Focus | Gap Addressed |
|------|-------|---------------|
| `04-large-file-evals.md` | 1000+ line files, sequential edits, deep nesting | Current max test file is ~300 lines. Real files are 500-2000+ lines. |
| `05-realistic-typescript-evals.md` | React components, import graphs, generics, JSX | Current test files are trivial single-line functions. |
| `06-anchor-stress-evals.md` | Near-duplicates, ambiguity resolution, adversarial anchors | Only tests obvious exact duplicates. Real code has subtler ambiguity. |

These specs are incomplete — each has identified the evals needed but requires further research on file generation, realistic patterns, and assertion design before implementation.

## Current Test Coverage

| Layer | Tests | File Sizes | Gaps |
|-------|-------|------------|------|
| Layer 1 (edit engine) | 36 | Up to 600 lines | No complex structure, no repetitive patterns |
| Layer 2 (tools) | 10 (+1 skip) | 50-200 lines | Adequate for tool correctness |
| Layer 3 (agent evals) | 10 | 1-300 lines | Files too small and simple vs real codebases |

## Running

```bash
# Fast (no LLM, seconds):
pytest tests/test_edit_engine.py tests/test_tools.py tests/test_git_helpers.py -v

# Agent evals (live LLM, ~100s, costs tokens):
pytest tests/evals/ -v --timeout=180
```
