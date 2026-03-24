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
    setup_files: dict[str, str]          # path -> content
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
