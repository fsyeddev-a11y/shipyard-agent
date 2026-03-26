# Spec 02: Layer 3 — Eval Framework + E-3.1 through E-3.4

## Objective
Create the eval framework for agent-level end-to-end testing, then implement the first 4 evals (E-3.1 through E-3.4). These involve the real LLM — they set up a codebase, send an instruction, and check the outcome.

## Dependencies
- All phases complete (agent loop, tools, session manager, tracing)
- `SHIPYARD_OPENAI_API_KEY` must be set in `.env`

## Directory Structure

```
tests/
└── evals/
    ├── __init__.py
    ├── framework.py             # AgentEval, assertions, runner
    ├── fixtures/                # Known codebase states for evals
    │   ├── single_edit/
    │   │   └── utils.ts
    │   ├── multi_file/
    │   │   ├── types.ts
    │   │   ├── service.ts
    │   │   └── handler.ts
    │   └── large_file/
    │       └── large.ts
    └── test_agent_evals.py      # E-3.1 through E-3.4 (this spec), E-3.5+ (spec 03)
```

## File: `tests/evals/__init__.py`

Empty file.

## File: `tests/evals/framework.py`

### Design

```python
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import time
from shipyard.edit_engine.git import git_init_if_needed
from shipyard.agent.supervisor import run_agent
from shipyard.config import ShipyardConfig


# --- Assertions ---

@dataclass
class FileContainsAssertion:
    """Check that a file contains a specific string after the agent runs."""
    file_path: str
    expected_content: str

    def check(self, project_root: Path) -> tuple[bool, str]:
        f = project_root / self.file_path
        if not f.exists():
            return False, f"File {self.file_path} does not exist"
        content = f.read_text()
        if self.expected_content in content:
            return True, ""
        return False, f"File {self.file_path} does not contain: {self.expected_content!r}"


@dataclass
class FileNotContainsAssertion:
    """Check that a file does NOT contain something."""
    file_path: str
    unexpected_content: str

    def check(self, project_root: Path) -> tuple[bool, str]:
        f = project_root / self.file_path
        if not f.exists():
            return True, ""
        content = f.read_text()
        if self.unexpected_content not in content:
            return True, ""
        return False, f"File {self.file_path} still contains: {self.unexpected_content!r}"


@dataclass
class FileExistsAssertion:
    """Check that a file exists."""
    file_path: str

    def check(self, project_root: Path) -> tuple[bool, str]:
        if (project_root / self.file_path).exists():
            return True, ""
        return False, f"File {self.file_path} does not exist"


@dataclass
class FileNotChangedAssertion:
    """Check that a file is identical to its setup content."""
    file_path: str
    original_content: str = ""  # set during setup by run_eval

    def check(self, project_root: Path) -> tuple[bool, str]:
        f = project_root / self.file_path
        if not f.exists():
            return False, f"File {self.file_path} does not exist"
        current = f.read_text()
        if current == self.original_content:
            return True, ""
        return False, f"File {self.file_path} was modified (expected unchanged)"


@dataclass
class GitCommitCountAssertion:
    """Check that the agent made the expected number of commits (above setup baseline)."""
    min_commits: int
    max_commits: int
    # baseline set by run_eval
    _baseline: int = 0


# --- Eval Definition ---

@dataclass
class AgentEval:
    """Definition of a single agent evaluation."""
    name: str
    setup_files: dict[str, str]          # path → content
    instruction: str
    assertions: list                     # list of assertion objects
    max_iterations: int = 20


# --- Eval Result ---

@dataclass
class EvalResult:
    """Result of running an eval."""
    name: str
    passed: bool
    duration_seconds: float = 0.0
    assertion_results: list[dict] = field(default_factory=list)
    error: str | None = None
    tool_calls: int = 0


# --- Eval Runner ---

async def run_eval(eval_def: AgentEval, tmp_path: Path) -> EvalResult:
    """
    Execute a single agent eval.

    1. Set up temp git repo with known files
    2. Run the agent with the instruction
    3. Check all assertions
    4. Return results
    """
    start_time = time.time()

    # 1. Setup: init git repo and create files
    git_init_if_needed(tmp_path)

    for file_path, content in eval_def.setup_files.items():
        full_path = tmp_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        subprocess.run(["git", "add", file_path], cwd=tmp_path)

    subprocess.run(
        ["git", "commit", "-m", "eval setup: initial files"],
        cwd=tmp_path, capture_output=True,
    )

    # Record baseline commit count
    baseline = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    baseline_commits = int(baseline.stdout.strip())

    # Set original_content on FileNotChangedAssertions
    for assertion in eval_def.assertions:
        if isinstance(assertion, FileNotChangedAssertion):
            f = tmp_path / assertion.file_path
            if f.exists():
                assertion.original_content = f.read_text()
        if isinstance(assertion, GitCommitCountAssertion):
            assertion._baseline = baseline_commits

    # 2. Run agent
    config = ShipyardConfig(project_root=tmp_path)
    tool_calls = 0

    try:
        async for event in run_agent(eval_def.instruction, config):
            if event.get("type") == "tool_call":
                tool_calls += 1
            elif event.get("type") == "done":
                break
    except Exception as e:
        duration = time.time() - start_time
        return EvalResult(
            name=eval_def.name, passed=False,
            duration_seconds=duration, error=str(e),
        )

    # 3. Check assertions
    all_passed = True
    assertion_results = []

    for assertion in eval_def.assertions:
        if isinstance(assertion, GitCommitCountAssertion):
            current = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=tmp_path, capture_output=True, text=True,
            )
            agent_commits = int(current.stdout.strip()) - assertion._baseline
            passed = assertion.min_commits <= agent_commits <= assertion.max_commits
            msg = f"Agent made {agent_commits} commits (expected {assertion.min_commits}-{assertion.max_commits})"
            assertion_results.append({"assertion": "GitCommitCount", "passed": passed, "detail": msg})
            if not passed:
                all_passed = False
        else:
            passed, msg = assertion.check(tmp_path)
            assertion_results.append({
                "assertion": type(assertion).__name__, "passed": passed, "detail": msg,
            })
            if not passed:
                all_passed = False

    duration = time.time() - start_time
    return EvalResult(
        name=eval_def.name, passed=all_passed,
        duration_seconds=duration, assertion_results=assertion_results,
        tool_calls=tool_calls,
    )
```

## Fixtures

Create fixture files that can also be loaded programmatically. For E-3.1 through E-3.4, the setup files are small enough to inline in the test. The `fixtures/` directory is for larger setups used in E-3.5+.

### `tests/evals/fixtures/single_edit/utils.ts`
```typescript
export function add(a: number, b: number): number { return a + b; }
```

### `tests/evals/fixtures/multi_file/types.ts`
```typescript
export interface User {
  id: string;
  name: string;
}
```

### `tests/evals/fixtures/multi_file/service.ts`
```typescript
import { User } from "./types";
export function createUser(name: string): User {
  return { id: crypto.randomUUID(), name };
}
```

### `tests/evals/fixtures/multi_file/handler.ts`
```typescript
import { createUser } from "./service";
export function handleSignup(name: string) {
  const user = createUser(name);
  return user;
}
```

### `tests/evals/fixtures/large_file/large.ts`
Generate a ~300 line TypeScript file with multiple functions. Create this programmatically in the test setup, not as a static fixture. The spec 03 test that needs it will generate it.

## File: `tests/evals/test_agent_evals.py` (E-3.1 through E-3.4)

```python
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
```

## pyproject.toml Update

Add `pytest-timeout` to dev dependencies if not present:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-timeout>=2.3.0",
    "ruff>=0.7.0",
]
```

## Implementation Notes

- Layer 3 tests live in `tests/evals/` — separate from fast unit tests
- Run Layer 1+2: `pytest tests/test_edit_engine.py tests/test_tools.py -v` (fast, no LLM)
- Run Layer 3: `pytest tests/evals/ -v --timeout=120` (slow, costs tokens)
- The `framework.py` file is `framework.py` NOT `eval_framework.py` (per user's structure)
- Fixture files are created in `tests/evals/fixtures/` for reuse across evals
- E-3.1 through E-3.4 inline their setup files since they're small
- `_assert_eval` provides detailed failure output including which assertions failed

## Acceptance Criteria
- [ ] `tests/evals/framework.py` has all assertion classes and `run_eval`
- [ ] `tests/evals/test_agent_evals.py` has E-3.1 through E-3.4
- [ ] Fixture files created in `tests/evals/fixtures/`
- [ ] `pytest tests/evals/test_agent_evals.py -v --timeout=120` — all 4 evals pass
- [ ] Eval failures show detailed assertion output
- [ ] `pytest-timeout` in dev dependencies
