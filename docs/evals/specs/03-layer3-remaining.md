# Spec 03: Layer 3 — E-3.5 through E-3.10

## Objective
Add the remaining 6 agent evals to `tests/evals/test_agent_evals.py`. These test harder scenarios: multi-file edits, search-then-edit, error handling, context injection, large files, and file precision.

## Dependencies
- Spec 02 (framework + E-3.1 through E-3.4) must be complete and passing

## Add to: `tests/evals/test_agent_evals.py`

### E-3.5: Multi-file edit (cross-file refactor)

```python
@pytest.mark.asyncio
@pytest.mark.timeout(180)  # longer timeout for multi-file
async def test_e3_5_multi_file_edit(tmp_path):
    """E-3.5: Agent adds email field across 3 files."""
    eval_def = AgentEval(
        name="E-3.5: Multi-file edit",
        setup_files={
            "src/types.ts": (
                "export interface User {\n"
                "  id: string;\n"
                "  name: string;\n"
                "}\n"
            ),
            "src/service.ts": (
                'import { User } from "./types";\n'
                "export function createUser(name: string): User {\n"
                "  return { id: crypto.randomUUID(), name };\n"
                "}\n"
            ),
            "src/handler.ts": (
                'import { createUser } from "./service";\n'
                "export function handleSignup(name: string) {\n"
                "  const user = createUser(name);\n"
                "  return user;\n"
                "}\n"
            ),
        },
        instruction=(
            "Add an email field to the User interface in types.ts, "
            "update createUser in service.ts to accept email as a parameter, "
            "and update handleSignup in handler.ts to pass email to createUser"
        ),
        assertions=[
            FileContainsAssertion("src/types.ts", "email"),
            FileContainsAssertion("src/service.ts", "email"),
            FileContainsAssertion("src/handler.ts", "email"),
            GitCommitCountAssertion(min_commits=2, max_commits=6),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)
```

### E-3.6: Agent uses search before editing (discovery)

```python
@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_e3_6_search_then_edit(tmp_path):
    """E-3.6: Agent finds and updates validateEmail without breaking callers."""
    eval_def = AgentEval(
        name="E-3.6: Search then edit",
        setup_files={
            "src/utils/format.ts": 'export function formatDate(d: Date) { return d.toISOString(); }\n',
            "src/utils/validate.ts": 'export function validateEmail(e: string) { return e.includes("@"); }\n',
            "src/utils/index.ts": (
                'export { formatDate } from "./format";\n'
                'export { validateEmail } from "./validate";\n'
            ),
            "src/components/UserForm.tsx": (
                'import { validateEmail } from "../utils";\n'
                "export function UserForm() {\n"
                '  const valid = validateEmail("test@example.com");\n'
                "  return valid;\n"
                "}\n"
            ),
        },
        instruction=(
            "The validateEmail function is too simple. "
            "Update it to use a proper regex pattern. Make sure nothing else breaks."
        ),
        assertions=[
            FileNotContainsAssertion("src/utils/validate.ts", 'e.includes("@")'),
            FileNotChangedAssertion("src/utils/format.ts"),
            FileNotChangedAssertion("src/components/UserForm.tsx"),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)
```

### E-3.7: Agent handles edit failure gracefully

```python
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e3_7_handles_missing_function(tmp_path):
    """E-3.7: Agent recognizes target function doesn't exist, doesn't corrupt file."""
    eval_def = AgentEval(
        name="E-3.7: Handles missing function",
        setup_files={
            "src/app.ts": (
                "const config = loadConfig();\n"
                "startServer(config);\n"
            ),
        },
        instruction="Update the function processPayment in src/app.ts to add logging",
        assertions=[
            FileNotChangedAssertion("src/app.ts"),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)
```

### E-3.8: Context injection mid-task

```python
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e3_8_context_injection(tmp_path):
    """E-3.8: Agent uses injected context (attached with instruction)."""
    eval_def = AgentEval(
        name="E-3.8: Context injection",
        setup_files={
            "src/api.ts": 'export function fetchData() { return fetch("/api/data"); }\n',
        },
        instruction=(
            'Update fetchData to include an auth header.\n\n'
            '---\nAttached context:\n'
            '{"auth_header": "Bearer token", "header_name": "Authorization"}'
        ),
        assertions=[
            FileContainsAssertion("src/api.ts", "Authorization"),
            FileContainsAssertion("src/api.ts", "Bearer"),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)
```

### E-3.9: Large file edit (200+ lines)

```python
@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_e3_9_large_file_edit(tmp_path):
    """E-3.9: Agent edits a function in a 300-line file without rewriting it."""
    # Generate a large TypeScript file
    lines = []
    lines.append("// Large module with multiple functions\n")
    for i in range(1, 11):
        lines.append(f"export function func{i}(x: number): number {{\n")
        lines.append(f"  // Function {i} does computation\n")
        for j in range(25):
            lines.append(f"  const step{j} = x + {j * i};\n")
        lines.append(f"  return x * {i};\n")
        lines.append("}\n\n")
    # Add the target function
    lines.append("export function processOrder(order: any): any {\n")
    lines.append("  const total = order.items.reduce((sum, item) => sum + item.price, 0);\n")
    lines.append("  return { ...order, total };\n")
    lines.append("}\n")

    large_content = "".join(lines)

    eval_def = AgentEval(
        name="E-3.9: Large file edit",
        setup_files={
            "src/large.ts": large_content,
        },
        instruction="Add input validation to the processOrder function in src/large.ts — check that order is not null and has an items array",
        assertions=[
            FileContainsAssertion("src/large.ts", "processOrder"),
            # File should still have ~300+ lines (not rewritten from scratch)
            FileContainsAssertion("src/large.ts", "func1"),
            FileContainsAssertion("src/large.ts", "func10"),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)

    # Extra check: file length is still large (not rewritten)
    final_content = (tmp_path / "src/large.ts").read_text()
    line_count = len(final_content.splitlines())
    assert line_count > 250, f"File was likely rewritten — only {line_count} lines (expected 300+)"
```

### E-3.10: Agent doesn't touch files it shouldn't

```python
@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e3_10_file_precision(tmp_path):
    """E-3.10: Agent only modifies the target file, leaves others alone."""
    eval_def = AgentEval(
        name="E-3.10: File precision",
        setup_files={
            "src/auth.ts": (
                "export function login(username: string, password: string) {\n"
                "  // authenticate user\n"
                "  return { token: 'abc123' };\n"
                "}\n"
            ),
            "src/dashboard.ts": (
                "export function renderDashboard() {\n"
                "  return '<div>Dashboard</div>';\n"
                "}\n"
            ),
            "src/database.ts": (
                "export function query(sql: string) {\n"
                "  // run database query\n"
                "  return [];\n"
                "}\n"
            ),
            "README.md": "# My Project\n\nA sample project.\n",
        },
        instruction="Add rate limiting to the login function in src/auth.ts",
        assertions=[
            FileNotChangedAssertion("src/dashboard.ts"),
            FileNotChangedAssertion("src/database.ts"),
            FileNotChangedAssertion("README.md"),
            GitCommitCountAssertion(min_commits=1, max_commits=3),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)
```

## Implementation Notes

- E-3.5 and E-3.6 get 180s timeout — multi-file tasks take longer
- E-3.7 tests graceful failure — the agent should NOT modify the file since processPayment doesn't exist
- E-3.8 inlines the context in the instruction (simulates attached context). True mid-execution injection via `/inject` would require a running server — save that for a later enhancement.
- E-3.9 generates the large file programmatically (~300 lines). Checks that all 10 original functions still exist (proves the file wasn't rewritten from scratch).
- E-3.10 is a precision test — auth.ts should be modified, but the other 3 files must be untouched.
- All tests use the same `_assert_eval` helper from spec 02.

## Acceptance Criteria
- [ ] E-3.5 through E-3.10 added to `test_agent_evals.py`
- [ ] `pytest tests/evals/test_agent_evals.py -v --timeout=180` — all 10 evals pass
- [ ] Multi-file edit (E-3.5) modifies all 3 files
- [ ] Search-then-edit (E-3.6) doesn't break callers
- [ ] Missing function (E-3.7) leaves file unchanged
- [ ] Large file (E-3.9) verifies file wasn't rewritten from scratch
- [ ] File precision (E-3.10) verifies unrelated files untouched
