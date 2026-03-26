# Spec 04: Large File & Complex Structure Evals

> **STATUS: INCOMPLETE — needs further planning and research.**
> This spec identifies the gaps but the exact eval definitions, file contents, and assertions need to be fleshed out after analyzing real-world editing patterns.

## Problem

Current evals use trivially small files (1-7 lines for most, ~300 lines max). Real codebases have files with 500-2000+ lines, deeply nested structures, and repetitive patterns. The edit engine and agent behavior on large, realistic files is untested.

## Planned Evals

### E-4.1: Large file edit near top (1000+ lines)

- Setup: Generate a ~1000 line TypeScript file (classes, functions, imports)
- Edit a function near the top (lines 10-20)
- Verify: correct edit, file integrity, rest of file untouched
- Risk: diff context lines at file boundary, agent might read too little context

### E-4.2: Large file edit near bottom (1000+ lines)

- Setup: Same ~1000 line file
- Edit a function near the bottom (lines 950-960)
- Verify: correct edit, earlier functions untouched
- Risk: agent might not scroll far enough, anchor might need more context

### E-4.3: Multiple sequential edits to same large file

- Setup: ~500 line file
- Instruction: make 3 separate changes to different functions
- Verify: all 3 changes applied, no context drift between edits
- Risk: after edit 1, the file content shifts — agent must re-read before edit 2

### E-4.4: Deeply nested structure

- Setup: File with 4+ levels of nesting (class > method > if/else > loop)
- Edit inside the deepest nesting level
- Verify: correct indentation preserved, surrounding structure intact
- Risk: whitespace normalization might mangle deeply indented code

### E-4.5: File with repetitive patterns

- Setup: File with 5+ similar function signatures (e.g., `handleCreate`, `handleUpdate`, `handleDelete` all with similar bodies)
- Edit only `handleUpdate`
- Verify: only the target function changed, similar functions untouched
- Risk: anchor ambiguity — if function bodies are too similar, `old_content` might match multiple locations

## Research Needed

- What are typical file sizes in real TypeScript projects? (Ship app analysis)
- What's the distribution of edit locations (top/middle/bottom)?
- How often do LLMs produce ambiguous anchors on real code?
- Should we generate test files programmatically or use curated realistic fixtures?
- What token cost overhead do large file reads add? (context budget pressure)
