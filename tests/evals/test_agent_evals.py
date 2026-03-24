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
