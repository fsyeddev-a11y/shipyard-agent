# FUTURE-SPECS.md — Shipyard Agent Enhancement Roadmap

## Purpose

This document defines incremental improvements to Shipyard based on studying how Claude Code, Codex, Cursor, and OpenCode work. Each enhancement is a self-contained spec with acceptance criteria and benchmark evals. Implement them iteratively — add one feature, benchmark, confirm no regression, then move to the next.

---

## Benchmarking Framework

### Philosophy

Every feature added to the agent should be measurable. Before adding a feature, define what "better" means. After adding it, prove it. If a new feature makes one thing better but causes regression elsewhere, the benchmark catches it.

### Benchmark Layers

```
Layer 0: Edit Engine (deterministic, no LLM)
  → Does the edit engine correctly apply edits?
  → Speed: edits per second on files of varying size

Layer 1: Tool Reliability (deterministic, no LLM)
  → Does each tool produce correct output given known input?
  → Edge case coverage

Layer 2: Single-Agent Task Completion (LLM-in-the-loop)
  → Given instruction + known codebase, does the agent produce the correct change?
  → Metrics: pass rate, tool calls, tokens, time, retries, precision

Layer 3: Multi-Agent Task Completion (LLM-in-the-loop)
  → Given instruction requiring coordination, do workers produce correct combined output?
  → Metrics: same as Layer 2 + coordination overhead, merge conflicts

Layer 4: Robustness (LLM-in-the-loop, adversarial)
  → Does the agent handle bad inputs, missing files, ambiguous instructions, large files?
  → Metrics: graceful failure rate, hallucination rate, files incorrectly touched
```

### Benchmark Runner

```python
# benchmarks/runner.py

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime

@dataclass
class BenchmarkResult:
    benchmark_id: str
    layer: int
    name: str
    passed: bool
    tool_calls: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    time_seconds: float = 0.0
    retries: int = 0
    files_touched: list[str] = field(default_factory=list)
    files_should_touch: list[str] = field(default_factory=list)
    files_incorrectly_touched: list[str] = field(default_factory=list)
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class BenchmarkSuite:
    suite_name: str
    git_commit: str          # which version of Shipyard was tested
    results: list[BenchmarkResult] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.passed) / len(self.results)
    
    @property
    def avg_tool_calls(self) -> float:
        llm_results = [r for r in self.results if r.tool_calls > 0]
        if not llm_results:
            return 0.0
        return sum(r.tool_calls for r in llm_results) / len(llm_results)
    
    @property
    def avg_tokens(self) -> float:
        llm_results = [r for r in self.results if r.tokens_input > 0]
        if not llm_results:
            return 0.0
        return sum(r.tokens_input + r.tokens_output for r in llm_results) / len(llm_results)
    
    @property
    def precision(self) -> float:
        """What % of file touches were correct (no files incorrectly touched)?"""
        relevant = [r for r in self.results if r.files_should_touch]
        if not relevant:
            return 1.0
        correct = sum(1 for r in relevant if not r.files_incorrectly_touched)
        return correct / len(relevant)
    
    def summary(self) -> dict:
        return {
            "suite": self.suite_name,
            "git_commit": self.git_commit,
            "timestamp": datetime.now().isoformat(),
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "pass_rate": round(self.pass_rate, 3),
            "precision": round(self.precision, 3),
            "avg_tool_calls": round(self.avg_tool_calls, 1),
            "avg_tokens": round(self.avg_tokens, 0),
            "by_layer": self._by_layer()
        }
    
    def _by_layer(self) -> dict:
        layers = {}
        for r in self.results:
            if r.layer not in layers:
                layers[r.layer] = {"passed": 0, "failed": 0, "total": 0}
            layers[r.layer]["total"] += 1
            if r.passed:
                layers[r.layer]["passed"] += 1
            else:
                layers[r.layer]["failed"] += 1
        return layers
    
    def save(self, path: str = "/.shipyard/benchmarks/"):
        """Append results to benchmark history for regression tracking."""
        import os
        os.makedirs(path, exist_ok=True)
        filepath = os.path.join(path, "history.jsonl")
        with open(filepath, "a") as f:
            f.write(json.dumps(self.summary()) + "\n")
        # Also save detailed results
        detail_path = os.path.join(path, f"run_{self.git_commit[:8]}_{int(time.time())}.json")
        with open(detail_path, "w") as f:
            json.dump([asdict(r) for r in self.results], f, indent=2)
```

### Regression Detection

```python
# benchmarks/regression.py

def check_regression(current: BenchmarkSuite, history_path: str = "/.shipyard/benchmarks/history.jsonl") -> list[str]:
    """Compare current run against last run. Flag regressions."""
    warnings = []
    
    # Load last run
    with open(history_path) as f:
        lines = f.readlines()
    if len(lines) < 2:
        return []  # no previous run to compare
    
    previous = json.loads(lines[-2])  # second-to-last line (last is current)
    current_summary = current.summary()
    
    # Check pass rate regression
    if current_summary["pass_rate"] < previous["pass_rate"]:
        warnings.append(
            f"REGRESSION: Pass rate dropped from {previous['pass_rate']} to {current_summary['pass_rate']}"
        )
    
    # Check precision regression
    if current_summary["precision"] < previous["precision"]:
        warnings.append(
            f"REGRESSION: Precision dropped from {previous['precision']} to {current_summary['precision']}"
        )
    
    # Check efficiency regression (>20% more tokens)
    if current_summary["avg_tokens"] > previous["avg_tokens"] * 1.2:
        warnings.append(
            f"REGRESSION: Avg tokens increased from {previous['avg_tokens']} to {current_summary['avg_tokens']} (+{((current_summary['avg_tokens']/previous['avg_tokens'])-1)*100:.0f}%)"
        )
    
    # Check per-layer regression
    for layer, stats in current_summary["by_layer"].items():
        prev_layer = previous.get("by_layer", {}).get(str(layer))
        if prev_layer and stats["total"] > 0 and prev_layer["total"] > 0:
            curr_rate = stats["passed"] / stats["total"]
            prev_rate = prev_layer["passed"] / prev_layer["total"]
            if curr_rate < prev_rate:
                warnings.append(
                    f"REGRESSION Layer {layer}: Pass rate dropped from {prev_rate:.2f} to {curr_rate:.2f}"
                )
    
    return warnings
```

### Running Benchmarks

```bash
# Run all layers (Layer 2+ costs tokens)
python -m benchmarks.run --all

# Run only deterministic tests (free, fast)
python -m benchmarks.run --layers 0 1

# Run specific layer
python -m benchmarks.run --layer 2

# Run and check for regressions
python -m benchmarks.run --all --check-regression

# Compare two runs
python -m benchmarks.compare <run_id_1> <run_id_2>
```

### Benchmark Storage

```
/.shipyard/benchmarks/
├── history.jsonl                              # one-line summary per run (for regression tracking)
├── run_abc123_1711300000.json                 # detailed results per run
├── run_def456_1711400000.json
└── ...
```

### Scorecard Format

After each run, print a scorecard:

```
╔══════════════════════════════════════════════════════════╗
║               SHIPYARD BENCHMARK SCORECARD              ║
║  Commit: abc1234  |  2026-03-25 14:30:00               ║
╠══════════════════════════════════════════════════════════╣
║  Layer 0 (Edit Engine):     14/14  100.0%               ║
║  Layer 1 (Tools):           11/11  100.0%               ║
║  Layer 2 (Single Agent):     8/10   80.0%  ⚠ -10%      ║
║  Layer 3 (Multi Agent):      3/4    75.0%  ✓ new       ║
║  Layer 4 (Robustness):       5/6    83.3%  ✓ +8.3%    ║
╠══════════════════════════════════════════════════════════╣
║  Overall:  41/45  91.1%                                 ║
║  Precision: 97.5%  |  Avg tokens: 12,400                ║
║  Avg tool calls: 8.3  |  Avg time: 34s                  ║
╠══════════════════════════════════════════════════════════╣
║  ⚠ REGRESSION: Layer 2 pass rate dropped 90% → 80%     ║
║    Failed: E-3.5 (multi-file refactor)                  ║
║    Failed: E-3.8 (context injection)                    ║
╚══════════════════════════════════════════════════════════╝
```

---

## Enhancement Specs

Each spec follows this format: what the feature is, why it matters, how to implement it, how to benchmark it, and what regressions to watch for.

---

### SPEC-01: Auto-Loading Project Context (CLAUDE.md equivalent)

**What:** On session start, automatically load `/.shipyard/PROJECT.md` into Tier 1 pinned context. On file access, auto-inject relevant notes from `/.shipyard/notes/` based on directory paths referenced in the current task.

**Why:** Currently the agent has to proactively call `read_notes`. Claude Code loads CLAUDE.md automatically, and subdirectory context lazily. The agent wastes tool calls discovering things it could know for free.

**Implementation:**
1. On session start: if `/.shipyard/PROJECT.md` exists, read it and append to Tier 1 pinned context
2. In the context manager's prompt assembly: scan the current instruction and recent tool calls for file paths. Extract directory names. Check if `/.shipyard/notes/{directory}.md` exists. If so, auto-inject into Tier 2 containers.
3. Track which notes were auto-injected so they can be evicted when the agent moves to a different area of the codebase.

**Benchmarks:**
- New eval: `E-auto-context-1`: Setup a project with `PROJECT.md` describing that "all API handlers use the `handleResult` wrapper." Give instruction "add a new endpoint." Assert the agent uses `handleResult` without being told to and without calling `read_notes`.
- New eval: `E-auto-context-2`: Setup notes for `auth/` directory. Give instruction mentioning `auth/login.ts`. Assert the agent's behavior reflects the note content without explicit `read_notes` call.
- Regression watch: Token usage should decrease (fewer `read_notes` tool calls). If token usage increases, the auto-injected context is too large — tighten the injection criteria.

---

### SPEC-02: Visible Task Tracker (TodoWrite equivalent)

**What:** A `update_plan` tool that writes the current task plan to `/.shipyard/current_plan.json` and logs it to JSONL. The plan is user-visible, survives crashes, and the agent updates status as steps complete.

**Why:** The edit plan currently lives in LangGraph worker state (invisible to user, lost on crash). Claude Code's TodoWrite makes the agent's progress transparent. Critical for the Ship rebuild where you need to see where the agent got stuck.

**Implementation:**
```python
# Tool: update_plan
# Input: list of plan items with status
@dataclass
class PlanItem:
    id: str
    description: str
    status: str  # pending | in_progress | completed | failed
    file: str | None = None

def update_plan(items: list[PlanItem]):
    plan = {"updated_at": timestamp, "items": [asdict(i) for i in items]}
    # Write to file (user-visible, crash-safe)
    write_json("/.shipyard/current_plan.json", plan)
    # Log to session JSONL
    log_event({"type": "plan_update", "items": plan["items"]})
```

Register as a tool available to both supervisor and workers. The supervisor calls it after decomposition. Workers call it as they complete steps.

**Benchmarks:**
- New eval: `E-plan-1`: Give a multi-step instruction. Assert `current_plan.json` exists after agent starts, has correct number of items, and all items reach `completed` status.
- New eval: `E-plan-crash`: Start a multi-step task, kill the process mid-way. Restart. Assert `current_plan.json` reflects partial progress and the agent can describe what was completed.
- Regression watch: Adding the tool should not increase tool call count significantly (the agent should call `update_plan` instead of some other tool, not in addition to). Check avg_tool_calls.

---

### SPEC-03: Persistent Shell Session

**What:** `run_command` maintains a persistent working directory across calls within a task. The agent can `cd src/` in one call and subsequent commands execute in that directory.

**Why:** Claude Code's `Bash` runs in a persistent shell session. Currently each `run_command` is independent — the agent has to pass the full `working_directory` every time. This wastes tokens on redundant path specifications and prevents stateful shell workflows.

**Implementation:**
- Maintain a `current_working_directory` in the session state, defaulting to project root
- If a command contains `cd`, parse the target directory and update `current_working_directory`
- All subsequent `run_command` calls use `current_working_directory` as the cwd unless explicitly overridden
- On task completion, reset to project root

**Benchmarks:**
- New eval: `E-shell-1`: Agent runs `cd src && ls` then `cat utils.ts` (without specifying directory). Assert the second command finds the file.
- Regression watch: Existing evals should pass unchanged. Check that `run_command` with explicit `working_directory` still overrides the persistent cwd.

---

### SPEC-04: Command Timeout and Long-Running Process Handling

**What:** `run_command` supports configurable timeouts, returns partial output on timeout, and can run commands in the background.

**Why:** If the agent runs `npm test` on a large project, it could take 60+ seconds. Currently unclear if `run_command` handles this gracefully. Claude Code's `Bash` handles background processes, output streaming, and kill signals.

**Implementation:**
- Default timeout: 120 seconds
- On timeout: kill the process, return whatever stdout/stderr was captured with a `[TIMEOUT after 120s]` marker
- Optional `background: true` parameter: start process, return immediately with a process ID
- `BashOutput` equivalent: check on a background process, get its latest output
- `KillShell` equivalent: kill a background process

**Benchmarks:**
- New eval: `E-timeout-1`: Run a command that sleeps for 200 seconds. Assert the tool returns within timeout with partial output and timeout marker.
- New eval: `E-background-1`: Start a dev server in background, run a curl against it, kill the server. Assert all three operations succeed.
- Regression watch: Existing command-based evals should not be affected. Check that fast commands still return quickly (no artificial delay from timeout mechanism).

---

### SPEC-05: Auto-Memory (Post-Task Learning)

**What:** After each completed task, middleware checks if the agent learned something reusable and writes it to notes automatically. Similar to Claude Code's MEMORY.md.

**Why:** Currently the agent only writes notes if it explicitly calls `write_note`. Most of the time it won't think to do this. Auto-memory captures patterns, conventions, and gotchas discovered during work without relying on the agent's initiative.

**Implementation:**
- Add an `after_task_complete` middleware hook
- After task completion, make a lightweight LLM call: "Given this task and its result, did you discover any reusable project knowledge? Respond with JSON: {learned: bool, topic: str, content: str} or {learned: false}"
- If `learned: true`, write to `/.shipyard/notes/{topic}.md`
- Use a cheap/fast model for this call (not the main model) to minimize cost
- Rate limit: max 1 auto-memory write per task to avoid note bloat

**Benchmarks:**
- New eval: `E-memory-1`: Agent completes a task that reveals a project pattern (e.g., "all API routes use the `withAuth` middleware"). On next task, assert the agent uses that pattern without being told.
- New eval: `E-memory-growth`: Run 10 tasks. Assert notes directory has ≤10 files (rate limiting works). Assert notes contain genuine patterns, not noise.
- Regression watch: Added LLM call per task increases cost. Track `tokens_per_task` metric. If auto-memory adds >5% to total tokens, the summarization prompt is too expensive — make it cheaper.

---

### SPEC-06: Diff Verification Hardening

**What:** Strengthen the edit engine's diff verification with additional checks and better error messages.

**Why:** The current verification checks hunks within anchor span and changed line count. Real-world edge cases need more coverage: whitespace-only diffs, encoding mismatches, edits that produce duplicate code, and diffs that technically pass but produce broken syntax.

**Implementation:**
1. Post-edit syntax check: after writing, run a fast syntax validator for the file type (e.g., `node --check` for JS, `python -c "import ast; ast.parse(open('f').read())"` for Python, `tsc --noEmit --pretty` for TypeScript). If it fails, revert and return the syntax error.
2. Duplicate code detection: after replacement, check if `new_content` appears more than once in the file. Warn if so (future edits may have ambiguous anchors).
3. Encoding preservation: detect file encoding before edit, ensure output matches. UTF-8 BOM, latin-1, etc.
4. Better error messages: on anchor-not-found, show the closest fuzzy match (Levenshtein distance) with a suggestion: "Did you mean this block on line 45?"

**Benchmarks:**
- New Layer 0 eval: `E-syntax-check`: Edit produces syntactically invalid code → assert revert + syntax error returned
- New Layer 0 eval: `E-duplicate-warning`: Edit creates duplicate anchor → assert warning in response
- New Layer 0 eval: `E-encoding`: Edit UTF-8 BOM file → assert BOM preserved after edit
- New Layer 0 eval: `E-fuzzy-match`: Anchor not found but similar block exists → assert suggestion in error message
- Regression watch: Syntax checking adds latency per edit. Benchmark edit speed before/after. If >100ms overhead per edit, make syntax checking configurable or async.

---

### SPEC-07: Tool Call Efficiency Benchmarks

**What:** Track and optimize how many tool calls the agent makes per task. Fewer calls = faster + cheaper.

**Why:** The difference between a good agent and a great one is efficiency. A naive agent might read every file in a directory to find a function. A smart one uses `search_files` first to narrow down. Claude Code has been optimized over millions of sessions. We can measure and improve.

**Implementation:**
No feature to build — this is a benchmark-only spec. Add efficiency metrics to every Layer 2+ eval:

```python
@dataclass
class EfficiencyMetrics:
    tool_calls_total: int
    tool_calls_by_type: dict[str, int]  # {"read_file": 3, "edit_file": 1, ...}
    unnecessary_reads: int               # files read but never edited or referenced
    redundant_reads: int                 # same file read multiple times
    search_before_read: bool             # did agent search before reading? (good pattern)
    tokens_total: int
    tokens_per_edit: float               # total tokens / number of edits made
```

Set baselines from the first full benchmark run. Flag when a change causes >20% increase in tool calls or tokens per edit.

**Benchmarks:**
- For each existing Layer 2+ eval, add efficiency tracking
- Define "efficient" thresholds per eval (e.g., E-3.1 single-line edit should take ≤5 tool calls)
- New eval: `E-efficiency-1`: 10-file project, instruction targets 1 file. Assert agent touches ≤3 files (search + read target + edit target). Flag if agent reads all 10.
- Regression watch: Any new feature that increases avg_tool_calls by >15% without improving pass_rate is a net negative.

---

### SPEC-08: Multi-Agent Benchmarks

**What:** Layer 3 benchmarks specifically for the multi-agent system. Tests supervisor decomposition, parallel worker execution, merge agent, and cross-worker validation.

**Why:** Multi-agent is the next phase after MVP. Having benchmarks ready before building ensures eval-first development continues.

**Implementation:**

```python
# New eval assertions for multi-agent
class WorkerCountAssertion:
    """Assert the supervisor spawned the expected number of workers."""
    expected_workers: int

class FileOwnershipAssertion:
    """Assert no two workers edited the same file."""
    pass

class SharedEditMergedAssertion:
    """Assert change_requests from workers were applied to shared files."""
    shared_file: str
    expected_content: str

class ParallelSpeedupAssertion:
    """Assert multi-agent was faster than sequential (wall clock)."""
    max_time_seconds: float
```

**Benchmarks:**
- `E-multi-1`: Two independent features (auth module + dashboard component). Assert 2 workers spawned, no file overlap, both features implemented correctly.
- `E-multi-2`: Feature requiring shared type updates. Assert workers use `request_shared_edit`, merge agent applies combined changes, types are correct.
- `E-multi-3`: One worker fails (bad instruction for its subtask). Assert other worker's changes are preserved, supervisor replans the failed subtask.
- `E-multi-4`: Deliberate file ownership conflict (supervisor assigns same file to two workers). Assert system catches this in decomposition, not at edit time.
- Regression watch: Multi-agent should not regress single-agent evals. Always run Layer 2 evals alongside Layer 3.

---

### SPEC-09: Robustness / Adversarial Benchmarks

**What:** Layer 4 benchmarks testing the agent against bad inputs, edge cases, and confusing scenarios.

**Why:** The Ship rebuild will throw unexpected situations at the agent. Benchmarking robustness before the rebuild means fewer surprises during.

**Benchmarks:**
- `E-robust-1`: Instruction references a file that doesn't exist. Assert agent reports the file doesn't exist, doesn't create a random file, doesn't hallucinate.
- `E-robust-2`: Instruction is ambiguous ("fix the bug"). Assert agent asks for clarification or reads test output to identify the bug, doesn't make random changes.
- `E-robust-3`: File has unusual encoding (UTF-16, latin-1). Assert agent can still read and edit it.
- `E-robust-4`: Very large file (2000+ lines). Assert agent reads targeted sections (line range), not the entire file. Assert edit works correctly.
- `E-robust-5`: Instruction asks to edit a binary file (image, compiled file). Assert agent refuses gracefully.
- `E-robust-6`: Circular dependency — instruction says "update function A to call B, and update B to call A." Assert agent handles this without infinite loop (might legitimately implement it, or might flag the circular dependency).
- `E-robust-7`: Conflicting instructions — "make the button red" followed by injected context "all buttons must be blue." Assert agent uses the most recent context.
- `E-robust-8`: Agent makes an edit that breaks the build. Assert it detects the break (via typecheck), reverts, and retries or reports.

---

## Implementation Order

Implement in this sequence. Run full benchmark suite after each. No next feature until regressions are resolved.

```
1. Benchmarking framework (runner, regression detection, scorecard)  ← DO FIRST
2. SPEC-07: Efficiency metrics on existing evals                     ← baseline measurement
3. SPEC-01: Auto-loading project context                             ← highest impact, low effort
4. SPEC-02: Visible task tracker                                     ← Ship rebuild prep
5. SPEC-06: Diff verification hardening                              ← correctness
6. SPEC-04: Command timeout + background processes                   ← robustness
7. SPEC-03: Persistent shell session                                 ← quality of life
8. SPEC-08: Multi-agent benchmarks                                   ← before building multi-agent
9. Build multi-agent system (Phase 5 from CODEAGENT-PLAN.md)
10. SPEC-09: Robustness benchmarks                                   ← before Ship rebuild
11. SPEC-05: Auto-memory                                             ← during/after Ship rebuild
```

Each step: implement → run full benchmark → check regression → fix regressions → commit → next step.
