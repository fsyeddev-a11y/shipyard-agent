# EVALS.md — Shipyard Evaluation Suite

## Philosophy

We know exactly what Shipyard needs to do. Write the evals first, build to pass them. Three layers: deterministic unit tests (edit engine), tool-level assertions (tools produce correct output given known input), and agent-level evals (given an instruction + codebase, agent produces the correct change).

Agent evals check the OUTCOME, not the path. The LLM can take different tool call sequences to reach the same result — that's fine. What matters: did the right file change in the right way, and did nothing else break?

---

## Layer 1: Edit Engine (Unit Tests)

Pure Python. No LLM. Deterministic. Already specified in CODEAGENT-PLAN.md.

### E-1.1: Anchor matching

- `anchor_found_once` → replacement applied
- `anchor_not_found` → error with file preview
- `anchor_ambiguous` → error requesting more context

### E-1.2: Diff verification

- `hunks_within_span` → verification passes
- `hunks_outside_span` → verification rejects
- `changed_lines_under_threshold` → passes
- `changed_lines_over_threshold` → rejects

### E-1.3: Atomicity

- `multi_edit_all_valid` → all applied, single commit
- `multi_edit_one_invalid` → none applied
- `multi_edit_reverse_order` → positions don't drift

### E-1.4: Edge cases

- `file_not_written_on_failure` → disk unchanged
- `git_commit_on_success` → commit exists with message
- `whitespace_normalized` → LLM output matches file conventions
- `large_file_edit` → works on 500+ line files
- `sequential_edits_same_file` → second edit sees first edit's result

---

## Layer 2: Tool-Level (Integration Tests)

Each test sets up a known filesystem state, calls a tool directly (not through the LLM), and asserts the output. No LLM involved.

### E-2.1: read_file

```
Setup: Create a file with 50 lines
Call: read_file("test.ts")
Assert: Output contains all 50 lines with line numbers prepended
```

```
Setup: Create a file with 200 lines
Call: read_file("test.ts", start_line=50, end_line=75)
Assert: Output contains only lines 50-75
```

### E-2.2: edit_file

```
Setup: Create test.ts with a function `function greet(name: string) { return "hello " + name; }`
Call: edit_file("test.ts", old_content='return "hello " + name', new_content='return `Hello, ${name}!`')
Assert: File on disk has the new return statement. Git log shows a commit. Diff summary returned.
```

```
Setup: Create test.ts with duplicate functions (same body appears twice)
Call: edit_file("test.ts", old_content="duplicate body")
Assert: Error returned — ambiguous anchor
```

### E-2.3: search_files

```
Setup: Create 5 files, 3 of which contain "createUser"
Call: search_files("createUser")
Assert: Returns 3 matches with file paths and line numbers
```

### E-2.4: run_command

```
Setup: Working directory with package.json
Call: run_command("echo hello world")
Assert: stdout contains "hello world"
```

```
Setup: None
Call: run_command("cat nonexistent_file")
Assert: stderr captured, returned to caller
```

### E-2.5: create_file

```
Setup: Empty directory
Call: create_file("src/utils.ts", "export function add(a, b) { return a + b; }")
Assert: File exists on disk with correct content
```

```
Setup: File already exists at path
Call: create_file("src/utils.ts", "new content")
Assert: Error — file already exists
```

### E-2.6: request_shared_edit

```
Setup: Orchestrator state initialized
Call: request_shared_edit("types/index.ts", "Add UserAuth type", old_content, new_content)
Assert: ChangeRequest added to orchestrator_state.change_requests. File NOT modified on disk.
```

### E-2.7: edit_file with ownership enforcement

```
Setup: ToolRegistry with files_owned=["auth.ts"]
Call: edit_file("dashboard.ts", old_content, new_content)
Assert: Error — file not owned by this worker
```

---

## Layer 3: Agent Behavior (End-to-End Evals)

These involve the LLM. Set up a known codebase state, send an instruction, check the outcome. Run against a real model via OpenAI.

### Eval Scaffolding

Each eval needs:

1. **Setup**: A temporary git repo with known files
2. **Instruction**: Natural language task for the agent
3. **Assertions**: Check filesystem state after agent completes
4. **Teardown**: Clean up temp repo

```python
# tests/evals/eval_framework.py

class AgentEval:
    name: str
    setup_files: dict[str, str]     # path → content
    instruction: str
    assertions: list[Assertion]      # checks to run after agent completes
    max_iterations: int = 20         # prevent runaway

class FileContainsAssertion:
    """Check that a file contains a specific string after the agent runs."""
    file_path: str
    expected_content: str

class FileNotContainsAssertion:
    """Check that a file does NOT contain something (old code was removed)."""
    file_path: str
    unexpected_content: str

class FileExistsAssertion:
    file_path: str

class FileNotChangedAssertion:
    """Check that a file the agent shouldn't have touched is identical to setup."""
    file_path: str

class GitCommitCountAssertion:
    """Check that the expected number of commits were made."""
    min_commits: int
    max_commits: int

class TypeCheckPassesAssertion:
    """Run tsc --noEmit and assert 0 errors."""
    pass
```

### E-3.1: Single-line edit

```
Setup files:
  src/utils.ts: 'export function add(a: number, b: number): number { return a + b; }'

Instruction: "Change the add function in src/utils.ts to subtract instead of add"

Assertions:
  - FileContainsAssertion("src/utils.ts", "a - b")
  - FileNotContainsAssertion("src/utils.ts", "a + b")
  - GitCommitCountAssertion(min=1, max=2)
```

### E-3.2: Add a function to an existing file

```
Setup files:
  src/math.ts: |
    export function add(a: number, b: number): number {
      return a + b;
    }

Instruction: "Add a multiply function to src/math.ts that takes two numbers and returns their product"

Assertions:
  - FileContainsAssertion("src/math.ts", "multiply")
  - FileContainsAssertion("src/math.ts", "a * b")  # or similar
  - FileContainsAssertion("src/math.ts", "export function add")  # original preserved
  - GitCommitCountAssertion(min=1, max=2)
```

### E-3.3: Create a new file

```
Setup files:
  src/index.ts: 'export { add } from "./math";'
  src/math.ts: 'export function add(a: number, b: number) { return a + b; }'

Instruction: "Create a new file src/constants.ts with a constant MAX_RETRIES set to 3 and a constant TIMEOUT_MS set to 5000"

Assertions:
  - FileExistsAssertion("src/constants.ts")
  - FileContainsAssertion("src/constants.ts", "MAX_RETRIES")
  - FileContainsAssertion("src/constants.ts", "3")
  - FileContainsAssertion("src/constants.ts", "TIMEOUT_MS")
  - FileContainsAssertion("src/constants.ts", "5000")
  - FileNotChangedAssertion("src/math.ts")  # didn't touch unrelated files
```

### E-3.4: Edit preserves surrounding code (surgical proof)

```
Setup files:
  src/config.ts: |
    export const config = {
      apiUrl: "http://localhost:3000",
      timeout: 5000,
      retries: 3,
      debug: false,
      logLevel: "info",
    };

Instruction: "Change the timeout in src/config.ts from 5000 to 10000"

Assertions:
  - FileContainsAssertion("src/config.ts", "timeout: 10000")
  - FileContainsAssertion("src/config.ts", 'apiUrl: "http://localhost:3000"')  # unchanged
  - FileContainsAssertion("src/config.ts", "retries: 3")                       # unchanged
  - FileContainsAssertion("src/config.ts", "debug: false")                     # unchanged
  - FileContainsAssertion("src/config.ts", 'logLevel: "info"')                 # unchanged
```

### E-3.5: Multi-file edit (cross-file refactor)

```
Setup files:
  src/types.ts: |
    export interface User {
      id: string;
      name: string;
    }
  src/service.ts: |
    import { User } from "./types";
    export function createUser(name: string): User {
      return { id: crypto.randomUUID(), name };
    }
  src/handler.ts: |
    import { createUser } from "./service";
    export function handleSignup(name: string) {
      const user = createUser(name);
      return user;
    }

Instruction: "Add an email field to the User interface in types.ts, update createUser in service.ts to accept email as a parameter, and update handleSignup in handler.ts to pass email to createUser"

Assertions:
  - FileContainsAssertion("src/types.ts", "email: string")
  - FileContainsAssertion("src/service.ts", "email")
  - FileContainsAssertion("src/handler.ts", "email")
  - GitCommitCountAssertion(min=2, max=6)  # at least one commit per file edited
```

### E-3.6: Agent uses search before editing (discovery)

```
Setup files:
  src/utils/format.ts: 'export function formatDate(d: Date) { return d.toISOString(); }'
  src/utils/validate.ts: 'export function validateEmail(e: string) { return e.includes("@"); }'
  src/utils/index.ts: 'export { formatDate } from "./format";\nexport { validateEmail } from "./validate";'
  src/components/UserForm.tsx: |
    import { validateEmail } from "../utils";
    // uses validateEmail somewhere

Instruction: "The validateEmail function is too simple. Update it to use a proper regex pattern. Make sure nothing else breaks."

Assertions:
  - FileContainsAssertion("src/utils/validate.ts", "regex")  # or RegExp or similar
  - FileNotContainsAssertion("src/utils/validate.ts", 'e.includes("@")')
  - FileNotChangedAssertion("src/utils/format.ts")            # unrelated file untouched
  - FileNotChangedAssertion("src/components/UserForm.tsx")     # caller unchanged (signature didn't change)
```

### E-3.7: Agent handles edit failure gracefully

```
Setup files:
  src/app.ts: |
    const config = loadConfig();
    startServer(config);

Instruction: "Update the function processPayment in src/app.ts to add logging"

Assertions:
  - Agent should recognize processPayment doesn't exist in the file
  - FileNotChangedAssertion("src/app.ts")  # file should be unchanged — agent couldn't find the target
  - Agent response should indicate the function was not found
```

### E-3.8: Context injection mid-task

```
Setup files:
  src/api.ts: 'export function fetchData() { return fetch("/api/data"); }'

Instruction: "Update fetchData to include an auth header"
Injected context (via /inject after instruction): '{"auth_header": "Bearer token", "header_name": "Authorization"}'

Assertions:
  - FileContainsAssertion("src/api.ts", "Authorization")
  - FileContainsAssertion("src/api.ts", "Bearer")
```

### E-3.9: Large file edit (200+ lines)

```
Setup files:
  src/large.ts: [Generate a 300-line TypeScript file with multiple functions]

Instruction: "Add input validation to the processOrder function in src/large.ts"

Assertions:
  - FileContainsAssertion("src/large.ts", some validation logic)
  - File still has ~300+ lines (wasn't rewritten from scratch)
  - Other functions in the file are unchanged
```

### E-3.10: Agent doesn't touch files it shouldn't

```
Setup files:
  src/auth.ts: [auth module]
  src/dashboard.ts: [dashboard module]
  src/database.ts: [database module]
  README.md: [project readme]

Instruction: "Add rate limiting to the login function in src/auth.ts"

Assertions:
  - FileContainsAssertion("src/auth.ts", "rate" or "limit")
  - FileNotChangedAssertion("src/dashboard.ts")
  - FileNotChangedAssertion("src/database.ts")
  - FileNotChangedAssertion("README.md")
```

---

## Running Evals

### Layer 1 + 2: Standard pytest

```bash
pytest tests/test_edit_engine.py tests/test_tools.py -v
```

These should run in seconds. No LLM calls. Run on every code change.

### Layer 3: Agent evals (require LLM, cost tokens)

```bash
pytest tests/evals/ -v --timeout=120
```

Each eval creates a temp git repo, runs the agent, checks assertions, tears down. Takes 30-60 seconds per eval depending on model speed. Costs tokens — don't run on every code change. Run before MVP submission and after significant changes.

### Eval Metrics to Track

For each Layer 3 eval run:

- **Pass/fail** — did all assertions pass?
- **Tool calls** — how many tool calls did the agent make? (Efficiency metric)
- **Tokens used** — input + output tokens (cost metric)
- **Time** — wall clock seconds to completion
- **Retries** — how many edit retries were needed? (Edit engine reliability metric)
- **Files touched** — did the agent touch only the files it should have? (Precision metric)

Log these to a JSONL file (`/.shipyard/eval_results.jsonl`) for tracking improvement over time.

---

## Eval-First Development Workflow

1. Write Layer 1 + 2 tests (edit engine + tools) — these define correctness
2. Build edit engine — pass Layer 1 tests
3. Build tools — pass Layer 2 tests
4. Write Layer 3 eval scaffolding (framework, assertions, setup/teardown)
5. Write E-3.1 through E-3.4 (single-agent evals)
6. Build single-agent loop — pass E-3.1 through E-3.4
7. Write E-3.5 through E-3.6 (multi-file, discovery evals)
8. Iterate agent prompts/tools until those pass
9. Write E-3.7 through E-3.10 (edge cases, robustness)
10. Harden agent until all pass
11. Multi-agent evals come with Phase 5

---

## Known Gaps (Planned Future Evals)

The current eval suite (E-1.x through E-3.10) uses small, simple files. The following areas are untested and have incomplete specs in `docs/evals/specs/`:

### Large File & Structure (spec 04)
- **1000+ line files**: current max is ~300 lines (E-3.9) and 600 lines (Layer 1). Real codebases have 500-2000+ line files.
- **Edits near file boundaries**: top/bottom of large files where diff context lines hit the edge.
- **Multiple sequential edits to the same large file**: context drift between edits.
- **Deeply nested code**: 4+ levels of indentation, risk of whitespace normalization issues.

### Realistic TypeScript (spec 05)
- **React components**: hooks, props, JSX — none of our test files use these patterns.
- **Import graphs**: renaming an export and updating all consumers.
- **Complex types**: generics, union types, mapped types.
- **Large config objects**: 50+ keys with similar structure, high ambiguity risk.

### Anchor Matching Stress (spec 06)
- **Near-duplicate functions**: similar signatures/bodies that could confuse anchor matching.
- **Same code in different scopes**: `return null` appearing in multiple functions.
- **Trailing whitespace variations**: LLM output vs file content mismatches.
- **Agent ambiguity resolution**: does the agent include enough context after an ambiguous anchor error?

These gaps represent the highest risk areas for the edit engine when operating on real codebases like the Ship app. Specs need further research and planning before implementation.
