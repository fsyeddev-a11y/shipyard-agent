# AI Development Log — Shipyard

## Tools & Workflow

| Tool | Usage |
|------|-------|
| **Claude Code (CLI)** | Primary development tool. Used for all code generation, architecture design, test writing, and documentation. Ran as persistent conversation with full codebase context. |
| **ChatGPT (DeepResearch)** | Pre-Search phase only. Used to research OpenCode, LangChain, and Claude Code architectures before writing code. Exported conversation as PRESEARCH.md. |
| **LangSmith** | Tracing and debugging agent runs. Every Shipyard agent invocation is traced — tool calls, LLM reasoning, token counts, latency all visible. Essential for diagnosing anchor matching failures. |
| **pytest** | Test runner for edit engine (36 tests), tools (11), git helpers (10), multi-agent (26), and agent evals (10 live LLM tests). |

**Workflow:** Research (ChatGPT) → Architecture (CLAUDE.md + REQUIREMENTS.md) → Implementation (Claude Code) → Testing (pytest) → Benchmarking (manual agent runs with BENCHMARKS.md tracking) → Iteration (system prompt + tool improvements based on benchmark data).

## Effective Prompts

### Prompt 1: Pre-Search Architecture Research
```
Study the OpenCode coding agent (github.com/sst/opencode). Read the source code for:
1. How it handles file editing — mechanism, tradeoffs, failure modes
2. How it manages context across turns (look at session/compaction.ts)
3. How it handles failed tool calls
Document findings with what to take and what to do differently.
```
**Why it worked:** Specific file paths and explicit "what to take / what to do differently" framing produced actionable research rather than surface-level summaries.

### Prompt 2: Edit Engine with Diff Verification
```
Implement the edit engine in shipyard/edit_engine/engine.py. Follow the 6-step pipeline from REQUIREMENTS.md exactly:
1. Read file → 2. Find anchor (exactly once) → 3. Normalize whitespace → 4. Replace → 5. Compute + verify diff → 6. Git commit.
Include apply_edit() and apply_edit_multi(). The multi variant validates ALL anchors before applying any, then applies bottom-to-top.
Write comprehensive tests in tests/test_edit_engine.py covering: anchor found/not found/ambiguous, diff within/outside span, atomic multi-edit, file not written on failure, git commit on success.
```
**Why it worked:** Referenced the exact spec (REQUIREMENTS.md), listed all steps, and explicitly requested tests alongside implementation. Produced 276 lines of engine code and 415 lines of tests in one pass.

### Prompt 3: System Prompt Iteration After Build 2
```
Build 2 had 9 interventions. Recurring issues:
1. Files created at root instead of packages/ (3 times)
2. Missing index.html for Vite (2 times)
3. Server verification hits 60s timeout

Update the system prompt to fix these. Don't add generic rules — add specific, actionable rules that address exactly these failures. Reference the actual framework patterns (React Router v6 syntax, sql.js result format, Express json() middleware).
```
**Why it worked:** Grounded in specific failure data (not hypothetical). The "don't add generic rules" instruction prevented prompt bloat. Produced system prompt v5 with framework-specific patterns that eliminated file placement issues in Build 3+.

### Prompt 4: Auto-Continue Loop Design
```
The agent hits LangGraph's message limit before completing multi-spec builds.
Design an auto-continue loop that:
1. Runs run_agent(), then checks .shipyard/notes/progress.md
2. If STATUS: COMPLETE not found, constructs a continue message and re-runs
3. Max 10 iterations
4. The continue message must be deterministic (no extra LLM call)
5. Include the original instruction + current progress in the continue message
Also add a post-completion audit that runs verify_checklist after STATUS: COMPLETE and can override back to IN_PROGRESS if checks fail.
```
**Why it worked:** Clear specification of the loop behavior, explicit "deterministic" constraint prevented over-engineering, and the audit system was designed alongside the loop rather than bolted on later.

### Prompt 5: Multi-Agent Implementation
```
Implement the multi-agent coordination system for Shipyard. The files to create/update:
- shipyard/agent/state.py — Pydantic models: SupervisorState, WorkerState, Subtask, ChangeRequest, WorkerResult, OrchestratorState
- shipyard/agent/worker.py — Worker LangGraph subgraph with file ownership enforcement
- shipyard/agent/merge_agent.py — Merge agent that applies deferred shared file edits
- shipyard/tools/request_shared_edit.py — Tool for workers to queue shared edits
- Update supervisor.py — Add decompose_task(), run_multi_agent() alongside existing single-agent flow
Write 26 tests covering: orchestrator state, state models, merge helpers, request_shared_edit, decomposition, file ownership.
Keep backward compatibility — single-agent mode must still work.
```
**Why it worked:** Listed every file with its responsibility, specified test count and coverage areas, and the "backward compatibility" constraint prevented breaking existing functionality.

## Code Analysis

| Category | Percentage |
|----------|-----------|
| AI-generated (Claude Code) | ~85% |
| AI-generated (Shipyard agent, during builds) | ~10% |
| Hand-written | ~5% |

The hand-written portion was primarily:
- Initial project scaffolding (pyproject.toml, directory structure)
- Bug fixes to system prompt rules (based on observing agent behavior in LangSmith traces)
- Manual dependency management during builds

## Strengths & Limitations

### Strengths
- **Architecture design:** Claude Code excelled at translating high-level requirements (REQUIREMENTS.md) into well-structured, modular code. The edit engine, context manager, and session system were all implemented correctly on the first pass.
- **Test generation:** Tests were comprehensive and caught real bugs. The 36 edit engine tests and 26 multi-agent tests were generated alongside the implementation code.
- **Iterative refinement:** Claude Code was effective at analyzing benchmark data (BENCHMARKS.md) and producing targeted system prompt improvements.

### Limitations
- **Framework-specific knowledge:** Both Claude Code and the Shipyard agent struggled with framework-specific patterns (React Router v6 vs v5, sql.js API, Vite entry points). This required explicit system prompt rules.
- **Dependency management:** Neither tool reliably installed all required dependencies. TypeScript `@types/*` packages were frequently missed.
- **Long-running process testing:** Testing servers that need to stay running while making HTTP requests was a consistent pain point until background process support was added.

## Key Learnings

1. **Benchmark everything.** Without BENCHMARKS.md tracking every intervention across 6 builds, I couldn't have identified which improvements actually mattered. The data showed that model quality (gpt-4o → gpt-5.4) was 3× more impactful than all system prompt improvements combined.

2. **System prompts have diminishing returns.** After ~15 rules, adding more rules doesn't help — the LLM starts ignoring them or they conflict. Better to inject knowledge via context (PRD, attached files) than to stuff the system prompt.

3. **Make the agent's work visible.** The notes system (plan.md, progress.md) was the single most important workflow improvement. It let me see exactly where the agent was stuck and what it was thinking, turning opaque failures into debuggable issues.

4. **File editing is the core differentiator.** The anchor-based edit engine with diff verification is what makes Shipyard a coding agent rather than a code generator. Investing heavily in testing this component (36 tests) paid off — zero edit engine failures in production.

5. **Auto-continue changes the game.** Without it, you're babysitting the agent prompt by prompt. With it, you fire a single instruction and come back to a completed build. The 10-iteration loop with progress-based continuation is simple but transforms the user experience.
