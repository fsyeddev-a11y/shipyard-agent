# Spec 06: Anchor Matching Stress Tests

> **STATUS: INCOMPLETE — needs further planning and research.**
> These test the edit engine's anchor matching under adversarial conditions. Mix of Layer 1 (deterministic) and Layer 3 (agent behavior) tests.

## Problem

The anchor-based editing strategy's biggest risk is ambiguity — `old_content` matching multiple locations. Current tests only check the obvious case (exact duplicate). Real codebases have subtler near-duplicates: similar function signatures, repeated patterns in different scopes, boilerplate code blocks.

## Planned Evals

### Layer 1 (Deterministic — edit engine)

**E-6.1: Near-duplicate functions**
- File has `createUser(name)` and `createUser(name, email)` — both contain `return { name }`
- old_content = `return { name }` → should be ambiguous (2 matches)
- old_content = `createUser(name: string): User {\n  return { name }` → should match exactly once

**E-6.2: Same code in different scopes**
- File has `if (x) { return null; }` appearing in two different functions
- Test that the engine correctly rejects ambiguous anchors
- Test that adding function name to anchor resolves ambiguity

**E-6.3: Anchor that spans a blank line**
- old_content includes a blank line between two code lines
- Verify the engine handles multi-line anchors with blanks correctly

**E-6.4: Anchor with trailing whitespace variations**
- old_content has trailing spaces that the file doesn't (or vice versa)
- Test that normalization handles this gracefully

### Layer 3 (Agent behavior)

**E-6.5: Agent resolves ambiguous anchor**
- Setup: file with two similar functions
- Instruction: edit one specific function
- Verify: agent includes enough context in old_content to be unambiguous
- This tests whether the system prompt's rule #3 ("include enough surrounding context") is effective

**E-6.6: Agent handles anchor-not-found gracefully**
- Setup: file where the obvious anchor doesn't exist (e.g., function was renamed)
- Instruction references the old name
- Verify: agent reads the file, discovers the issue, and adapts

## Research Needed

- Analyze common anchor ambiguity patterns in real TypeScript code
- What's the failure rate of anchor matching in the current eval suite? (Pull from session logs)
- Should we adjust the system prompt to give more specific guidance on anchor selection?
- Is there a heuristic for "minimum anchor size" that avoids most ambiguity?
