import pytest
from tests.evals.framework import (
    AgentEval, run_eval,
    FileContainsAssertion, FileNotContainsAssertion,
    FileExistsAssertion, FileNotChangedAssertion,
    GitCommitCountAssertion,
)


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e3_1_single_line_edit(tmp_path):
    """E-3.1: Agent changes add to subtract."""
    eval_def = AgentEval(
        name="E-3.1: Single-line edit",
        setup_files={
            "src/utils.ts": "export function add(a: number, b: number): number { return a + b; }\n",
        },
        instruction="Change the add function in src/utils.ts to subtract instead of add",
        assertions=[
            FileContainsAssertion("src/utils.ts", "a - b"),
            FileNotContainsAssertion("src/utils.ts", "a + b"),
            GitCommitCountAssertion(min_commits=1, max_commits=2),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e3_2_add_function(tmp_path):
    """E-3.2: Agent adds a multiply function to an existing file."""
    eval_def = AgentEval(
        name="E-3.2: Add function",
        setup_files={
            "src/math.ts": (
                "export function add(a: number, b: number): number {\n"
                "  return a + b;\n"
                "}\n"
            ),
        },
        instruction="Add a multiply function to src/math.ts that takes two numbers and returns their product",
        assertions=[
            FileContainsAssertion("src/math.ts", "multiply"),
            FileContainsAssertion("src/math.ts", "export function add"),
            GitCommitCountAssertion(min_commits=1, max_commits=2),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e3_3_create_new_file(tmp_path):
    """E-3.3: Agent creates a new file with constants."""
    eval_def = AgentEval(
        name="E-3.3: Create new file",
        setup_files={
            "src/index.ts": 'export { add } from "./math";\n',
            "src/math.ts": "export function add(a: number, b: number) { return a + b; }\n",
        },
        instruction="Create a new file src/constants.ts with a constant MAX_RETRIES set to 3 and a constant TIMEOUT_MS set to 5000",
        assertions=[
            FileExistsAssertion("src/constants.ts"),
            FileContainsAssertion("src/constants.ts", "MAX_RETRIES"),
            FileContainsAssertion("src/constants.ts", "3"),
            FileContainsAssertion("src/constants.ts", "TIMEOUT_MS"),
            FileContainsAssertion("src/constants.ts", "5000"),
            FileNotChangedAssertion("src/math.ts"),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_e3_4_surgical_edit(tmp_path):
    """E-3.4: Agent changes one value without touching surrounding code."""
    eval_def = AgentEval(
        name="E-3.4: Surgical edit",
        setup_files={
            "src/config.ts": (
                "export const config = {\n"
                '  apiUrl: "http://localhost:3000",\n'
                "  timeout: 5000,\n"
                "  retries: 3,\n"
                "  debug: false,\n"
                '  logLevel: "info",\n'
                "};\n"
            ),
        },
        instruction="Change the timeout in src/config.ts from 5000 to 10000",
        assertions=[
            FileContainsAssertion("src/config.ts", "timeout: 10000"),
            FileContainsAssertion("src/config.ts", 'apiUrl: "http://localhost:3000"'),
            FileContainsAssertion("src/config.ts", "retries: 3"),
            FileContainsAssertion("src/config.ts", "debug: false"),
            FileContainsAssertion("src/config.ts", 'logLevel: "info"'),
        ],
    )
    result = await run_eval(eval_def, tmp_path)
    _assert_eval(result)


@pytest.mark.asyncio
@pytest.mark.timeout(180)
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


def _assert_eval(result):
    """Helper: assert eval passed with details on failure."""
    if not result.passed:
        failures = [a for a in result.assertion_results if not a["passed"]]
        failure_details = "\n".join(f"  - {a['assertion']}: {a['detail']}" for a in failures)
        pytest.fail(
            f"Eval '{result.name}' failed:\n"
            f"Duration: {result.duration_seconds:.1f}s\n"
            f"Tool calls: {result.tool_calls}\n"
            f"Error: {result.error or 'None'}\n"
            f"Failed assertions:\n{failure_details}"
        )
