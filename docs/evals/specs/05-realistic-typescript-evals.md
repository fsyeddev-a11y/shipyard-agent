# Spec 05: Realistic TypeScript Evals

> **STATUS: INCOMPLETE — needs further planning and research.**
> Requires curating or generating realistic TypeScript files that resemble the Ship app codebase.

## Problem

Current eval files are trivial: single-line functions, no imports, no types, no JSX. The agent's ability to handle real TypeScript patterns (generics, interfaces, React components, import graphs) is untested.

## Planned Evals

### E-5.1: React component edit

- Setup: A realistic React functional component (50-100 lines) with hooks, props interface, JSX, event handlers
- Edit: Add a new prop and wire it into the JSX
- Verify: component structure intact, new prop used correctly, imports unchanged

### E-5.2: TypeScript interface + implementation update

- Setup: An interface file, an implementation file using that interface, and a test file
- Edit: Add a required field to the interface, update implementation to satisfy it
- Verify: type-level consistency across files (if we can run tsc)

### E-5.3: Import graph modification

- Setup: 4-5 files with an import graph (index.ts re-exports, util imported by multiple consumers)
- Edit: Rename an exported function
- Verify: all import sites updated, no broken references
- Risk: agent needs to search for all usages before editing

### E-5.4: Complex TypeScript types

- Setup: File with generics, union types, mapped types, conditional types
- Edit: Modify a generic type parameter
- Verify: downstream usages still type-correct

### E-5.5: Config/JSON-like structures

- Setup: Large configuration object (50+ keys, nested objects)
- Edit: Change a deeply nested value
- Verify: only the target value changed, rest of config identical
- Risk: similar-looking keys could cause ambiguous anchors

## Research Needed

- Analyze the Ship app's actual file patterns to build representative fixtures
- Determine if `tsc --noEmit` can be used as an assertion (TypeCheckPassesAssertion exists in EVALS.md but isn't implemented)
- Should these fixtures be checked into `tests/evals/fixtures/` or generated?
