# Phase 2: Edit Engine + Tests

## Goal
Implement the core edit engine — the deterministic Python code that performs surgical file edits with anchor-based matching and unified diff verification. This is the most scrutinized component in the system. No LLM calls — pure logic.

## Why This Matters
The edit engine is what separates a real coding agent from one that rewrites entire files. Every edit must:
1. Find the exact anchor in the file (no ambiguity)
2. Replace only the targeted block
3. Verify via unified diff that nothing outside the anchor was touched
4. Auto-commit via git on success
5. Refuse to write on verification failure

## Specs
Implement in order:

| Order | Spec | What It Produces |
|-------|------|-----------------|
| 1 | `01-normalize.md` | `shipyard/edit_engine/normalize.py` — whitespace/line ending detection and normalization |
| 2 | `02-diff.md` | `shipyard/edit_engine/diff.py` — unified diff computation, parsing, and verification |
| 3 | `03-engine.md` | `shipyard/edit_engine/engine.py` — core `apply_edit` and `apply_edit_multi` functions |
| 4 | `04-tests.md` | `tests/test_edit_engine.py` — comprehensive test suite |

## Dependencies
- Phase 1 must be complete (project structure, config, git helpers)
- The git helpers from `shipyard/edit_engine/git.py` are used by the engine for auto-commit

## Success Criteria
After Phase 2 is complete:
- `apply_edit()` handles single anchor-based replacements with diff verification
- `apply_edit_multi()` handles atomic multi-site edits (bottom-to-top ordering)
- All error cases return descriptive errors (anchor not found, ambiguous anchor, diff verification fail)
- Files are NOT written on verification failure
- Git auto-commit happens on every successful edit
- All tests pass: `pytest tests/test_edit_engine.py -v`
