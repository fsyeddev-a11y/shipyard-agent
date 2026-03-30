# AGENT-ISSUES.md — Recurring Issues, Gotchas, and System Prompt Candidates

Track recurring agent behavior problems here. Each entry is a candidate for a system prompt rule, tool improvement, or architecture fix. When we batch-update the system prompt, pull from this list.

---

## File Placement Errors

**Issue:** Agent creates files/folders at the wrong directory level. In a monorepo, it puts things at the project root instead of inside the correct package.

**Examples:**
- Created `shared/` at root AND inside `packages/shared/` (duplicate)
- Created `web/` at root instead of `packages/web/`

**Occurrences:** Helm Build 1 — Instructions 1, 2, 6

**Root cause:** Agent doesn't check existing project structure before creating files. It uses the path from the instruction literally instead of resolving it against what already exists on disk.

**Proposed fix:** System prompt rule: "Before creating any file, run list_files to understand the project structure. Place files relative to existing directories. If a packages/ or src/ directory already exists, create files inside it — never create a duplicate at the root." **STATUS: Rule added in Build 2 system prompt but agent still ignores it (3 occurrences across 2 builds).** Needs stronger wording — agent sees `packages/` in list_files but doesn't connect "web/src" to "packages/web/src". Proposed escalation: "CRITICAL: If a packages/ directory exists, ALL package references (api, web, shared) MUST use packages/ prefix. NEVER create api/, web/, or shared/ at the project root."

---

## Missing Essential Framework Files

**Issue:** When scaffolding a framework project (React + Vite), the agent creates config files but omits the actual entry points needed to run the app.

**Examples:**
- Created `vite.config.ts`, `package.json`, `tsconfig.json` but NOT `index.html` or `src/main.tsx`
- These are the two files Vite requires to serve anything

**Occurrences:** Helm Build 1 — Instructions 1, 7

**Root cause:** Agent treats each instruction literally and doesn't reason about what a framework needs to function. If the instruction says "set up React + Vite" it should know the minimum viable file set.

**Proposed fix:** System prompt rule: "When creating a project with a framework (React, Express, etc.), always create ALL files required for the framework to run, even if not explicitly listed in the instruction. For React + Vite: index.html and src/main.tsx are always required."

---

## Line Numbers in Anchors

**Issue:** The `read_file` tool returns content with line number prefixes (`" 1 | code here"`). The agent then uses these line-numbered strings as `old_content` in `edit_file`, which fails because the actual file doesn't contain line numbers.

**Examples:**
- Used `" 26 |   updatedAt: Date;"` as old_content — anchor not found
- Wasted 5 attempts before figuring out to strip line numbers

**Occurrences:** demo2 Test (cross-file priority refactor) — first attempt before system prompt fix

**Status:** FIXED in system prompt (Rule 3). Monitor for recurrence.

**Fix applied:** Added explicit rule: "CRITICAL: old_content and new_content must be the RAW file text. The read_file tool prepends line numbers — NEVER include those in old_content or new_content."

---

## Post-Completion Rambling / Recursion Limit

**Issue:** After completing all edits successfully, the agent continues generating text and making unnecessary tool calls instead of stopping. This burns through the LangGraph recursion limit.

**Examples:**
- Completed all edits for the priority field task, then kept talking and hit the 25-message recursion limit

**Occurrences:** demo2 Test (first cross-file edit attempt)

**Status:** PARTIALLY FIXED in system prompt (Rule 10: "When you are done with all changes, stop.")

**Proposed fix:** Consider also reducing verbosity in the system prompt — tell the agent to confirm changes briefly, not explain in detail.

---

## Dependency Installation Gaps

**Issue:** Agent creates source files that import packages but doesn't run `npm install` to install those packages. The project looks complete but fails to compile/run.

**Examples:**
- Created `api/src/index.ts` importing `express` but never ran `npm install express`
- Created files importing `react-router-dom` without installing it

**Occurrences:** Helm Build 1 — Instructions 1, 3, 7

**Root cause:** Agent treats file creation and dependency installation as separate concerns. It creates the code first and may or may not remember to install dependencies.

**Proposed fix:** System prompt rule: "When creating files that import external packages, always run the appropriate install command (npm install, pip install, etc.) in the same instruction. Do not leave unresolved imports."

---

## Edit Engine: Empty Anchor Causes Infinite Loop

**Issue:** When the agent creates a file with empty content and then tries to edit it with `old_content=''`, `_find_anchor` treats empty string as matching everywhere, returns a bad line number (-1), and diff verification fails with "Hunk starts at line -1". The agent retries the same edit forever until hitting the recursion limit.

**Examples:**
- Agent created `pages/WorkspacePage.tsx` with `content=''`, then tried `edit_file(old_content='', new_content='...')` — failed 15+ times identically

**Occurrences:** Helm Build 1 — cleanup prompt after Instruction 7

**Status:** FIXED — added empty anchor guard in `_find_anchor`: `if not anchor: return (0, -1, -1)`

---

## No Move/Delete File Tools

**Issue:** The agent has no way to move or delete files. When asked to reorganize project structure, it tries to create new files and copy content, but does this poorly — creates files with placeholder comments instead of actual code, or creates empty files and tries to edit them.

**Examples:**
- Asked to move pages from `components/` to `pages/` — created empty files, couldn't edit them
- Asked to move `web/` into `packages/web/` — created files with `// Content of X.tsx` comments instead of actual content

**Occurrences:** Helm Build 1 — structure cleanup prompts

**Root cause:** Tool suite only has create_file, not move_file or delete_file. The run_command tool can do `mv` and `rm` but the agent doesn't think to use it for file operations.

**Proposed fix:** Either add `move_file` and `delete_file` tools, or add a system prompt rule: "To move or delete files, use run_command with mv or rm. Do not create empty files and try to edit them."

---

## Agent Loops on Same Failing Edit

**Issue:** When an edit fails (verification_failed, anchor_not_found), the agent often retries the exact same edit with the exact same parameters instead of changing its approach. This wastes all remaining iterations.

**Examples:**
- edit_file with empty old_content failed 15 times with identical "Hunk starts at line -1" error — agent never changed strategy

**Occurrences:** Helm Build 1 — cleanup prompt

**Root cause:** The error message doesn't tell the agent what to do differently. The agent sees "verification_failed" but doesn't understand why.

**Proposed fix:** Improve edit engine error messages to include actionable guidance. E.g., "old_content is empty — use create_file for new content or provide the existing text to replace." Also system prompt rule: "If an edit fails twice with the same error, change your approach — do not retry the same edit."

---

## Horizontal vs Vertical: Agent Builds Breadth-First Instead of Depth-First

**Issue:** The agent works horizontally — creates all files/components in a single pass, then moves on. A real engineer works vertically — gets one thing working end-to-end, verifies it, then builds the next thing on top. The horizontal approach means errors compound silently and debugging becomes a cascade of 10+ fix prompts.

**Examples:**
- Build 1 Instruction 1: Agent created all config files (package.json, tsconfigs, vite.config) without verifying any of them compile. Missing dependencies weren't caught until much later.
- Build 1 Instruction 7: Agent created all 3 page components at once, none of them worked. Had to send 4+ separate prompts to fix each one individually.
- Build 1 API routes: Agent wrote all 5 CRUD routes in one pass. GET list worked but GET by id, PUT, and DELETE used wrong API (MongoDB methods on sql.js). If it had written and tested one route at a time, the mistake would have been caught immediately.

**Occurrences:** Every multi-file instruction in Build 1

**Root cause:** The system prompt doesn't tell the agent to verify its work incrementally. The agent optimizes for "completing the instruction" rather than "producing working code."

**Proposed fix:** System prompt rules:
1. "Work vertically, not horizontally. When building multiple things, get the first one working and verified before starting the second."
2. "After creating a file that should be runnable or importable, verify it works: run the compiler, start the server, or import it. Fix issues before moving on."
3. "After creating an API route, test it with run_command (curl). After creating a React component, check that the dev server shows no errors."
4. "If an instruction asks for multiple files, prioritize: create one → verify → create next. Do not create all files then hope they work together."

**Why this matters:** Vertical development catches errors at the source. A broken import caught immediately costs 1 edit to fix. The same broken import caught 5 files later costs 5+ edits because downstream code was built on the broken assumption.

---

## Server Verification Hits 60s Timeout

**Issue:** When the agent follows the "verify after creating" rule and tries to start a long-running server (Express, Vite dev server), `run_command` blocks for 60 seconds and then times out. The agent then wastes remaining messages trying alternative approaches (node, tsc, npm start) that all fail the same way, eventually hitting the recursion limit.

**Examples:**
- Build 2 Instruction 3: Agent ran `npm start` to verify Express server — timed out. Tried `node src/index.js` (wrong, it's TypeScript). Tried `tsc` (not installed). Tried `npm install -g typescript` (permission denied). Hit recursion limit.
- Build 1 had the same issue but the agent didn't try to verify, so it was hidden.

**Occurrences:** Build 2 — Instructions 3, potentially 7-8

**Root cause:** `run_command` uses `asyncio.create_subprocess_shell` with a 60s timeout. Servers don't exit — they listen forever. The tool has no background/detach mode.

**Proposed fix (short-term):** System prompt rule: "To verify a server starts correctly, use run_command to start it with a timeout: e.g., `timeout 5 npx tsx src/index.ts` — if it doesn't crash in 5 seconds, it's likely working. Or use `npx tsx src/index.ts &` with a subsequent `curl` and `kill %1`."

**Proposed fix (long-term):** Add background process support to `run_command` — a `background: true` parameter that starts the process, returns immediately with a PID, and provides a way to check output or kill it later. This is SPEC-04 in FUTURE-SPECS.md.

---

## Dependencies Not Fully Installed — Requires Manual npm install

**Issue:** Despite the system prompt rule to install dependencies, the agent still leaves packages partially installed. It installs the main package but misses type declarations (@types/*), peer dependencies, or dev dependencies. The user has to manually run `npm install` to fix imports before the code will run.

**Examples:**
- Build 2 Instruction 1: Agent created files importing `express` but didn't install `@types/express` or `@types/node`
- Build 2 Instruction 4: Agent created routes importing `uuid` but didn't install `uuid` or `@types/uuid`. Had to manually run `npm install uuid @types/uuid`
- Build 1 Instructions 1, 3, 7: Same pattern — missing dependencies required manual intervention each time

**Occurrences:** Every build, multiple instructions

**Root cause:** The system prompt says "install packages when creating files that import them" but the agent interprets this narrowly — it installs the main package and forgets the @types/* counterpart. It also doesn't verify imports resolve after installing.

**Proposed fix:**
1. System prompt rule: "When installing npm packages for TypeScript, ALWAYS install the @types/* package too. Example: npm install express && npm install -D @types/express @types/node. After installing, verify with a quick compile check."
2. Consider adding a post-install verification step: "After npm install, run npx tsc --noEmit to check for type errors."

---

## sql.js Returns Arrays, Agent Doesn't Map to Objects

**Issue:** When using sql.js, `db.exec()` returns `[{columns: [...], values: [[...]]}]` — raw arrays, not objects. The agent writes routes that return these arrays directly to the API response instead of mapping them to typed objects with camelCase field names.

**Examples:**
- Build 1 Instruction 4: API returned `["1","workspace","Engineering",...]` instead of `{"id":"1","type":"workspace",...}`
- Build 2 Instruction 4: Exact same issue — agent didn't map sql.js results to objects

**Occurrences:** Both builds, same instruction

**Root cause:** The agent doesn't know sql.js's response format. It assumes queries return objects like most ORMs. The snake_case → camelCase mapping (parent_id → parentId, created_at → createdAt) is also missed.

**Proposed fix:** System prompt rule: "When using sql.js, db.exec() returns {columns, values} — raw arrays. Always map results to typed objects. Map snake_case column names to camelCase for the API response." Alternatively, include a helper function pattern in the prompt for sql.js projects.

---

## Agent Can't Compile/Run TypeScript Without Help

**Issue:** The agent creates TypeScript files but doesn't know how to run them. It tries `node src/index.js` (wrong extension), `tsc` (not installed), and doesn't know about `tsx` or `ts-node`.

**Examples:**
- Build 2 Instruction 3: Agent tried `node src/index.js`, `tsc`, `npm install -g typescript` — none worked
- Build 1: Same issue, required manual `npx tsx` intervention

**Occurrences:** Build 1 Instruction 4, Build 2 Instruction 3

**Root cause:** System prompt doesn't specify how to run TypeScript. The agent guesses.

**Proposed fix:** System prompt rule: "To run TypeScript files, use `npx tsx <file>`. Install tsx as a dev dependency first: `npm install -D tsx`. Never use `node` directly on .ts files."

---

## Planning Phase Not Robust Enough

**Issue:** The agent's planning step is shallow. It lists what it will do ("I'll create these files") but doesn't specify exact file paths, doesn't verify where files should live relative to existing structure, and doesn't outline the change strategy for each file. This is the root cause of the file placement issue — the plan says "create Layout.tsx" but never resolves the full path.

**Examples:**
- Build 2 Instruction 6: Agent planned "Create Layout.tsx, DocumentCard.tsx, CreateDocumentForm.tsx" but created them at `web/src/components/` instead of `packages/web/src/components/`
- Build 2 Instruction 2: Planned "Create shared/types.ts" — created at root instead of packages/shared/

**Occurrences:** Every multi-file instruction across both builds

**Root cause:** The planning step doesn't include a "resolve paths" phase. The agent plans what to create but not where, relative to the actual project on disk.

**Proposed fix:** System prompt rule: "During planning, for EVERY file you will create or edit, write out the FULL path from project root. Run list_files first and resolve each path against what exists. Example plan: 'Create packages/web/src/components/Layout.tsx (confirmed packages/web/src/ exists)'. Never plan with partial paths like 'web/src/...' — always resolve to the full path."

---

## No Rollback on Failure

**Issue:** When the agent creates multiple files and a later one breaks the build, it doesn't undo earlier changes. Git auto-commits each file, but the agent never runs `git revert` when things go wrong. The project is left in a partially broken state.

**Examples:**
- Build 2 Instruction 7: Created App.tsx and main.tsx with conflicting BrowserRouter setups. Both were committed. Had to fix manually.

**Occurrences:** Both builds — every time a multi-file instruction partially fails

**Root cause:** No error recovery strategy. The agent only moves forward.

**Proposed fix:** System prompt rule: "If you create multiple files and discover one breaks the build, fix the broken file before creating more. If a fix isn't possible, note what needs manual intervention." Long-term: implement rollback logic in the agent loop.

---

## No Build/Compile Verification Loop

**Issue:** The agent creates TypeScript files but never runs `tsc --noEmit` to check types. It only discovers type errors when trying to run the server (which then times out). A quick compile check after each file would catch errors at the source.

**Examples:**
- Build 2 Instruction 4: Type errors in routes file only discovered when trying to start server
- Both builds: import path errors not caught until runtime

**Occurrences:** Both builds

**Proposed fix:** System prompt rule: "After creating or editing a TypeScript file, run `npx tsc --noEmit` to check for type errors. Fix any errors before moving to the next file." Requires tsx/typescript to be installed.

---

## Agent Can't Parse Its Own Error Output

**Issue:** When `run_command` returns an error, the agent often misinterprets the key line. It sees "command failed" but doesn't extract the actual error message to determine the fix. It may retry the same command or try unrelated fixes.

**Examples:**
- Build 2 Instruction 3: Agent saw "Error: Cannot find module" but tried `tsc` instead of fixing the module path
- Build 2 Instruction 4: Agent saw TypeScript errors but added a comment instead of fixing the type issue

**Occurrences:** Both builds — whenever run_command returns errors

**Root cause:** The agent reads error output as natural language rather than parsing it structurally (file path, line number, error code).

**Proposed fix:** Improve run_command output formatting to highlight the key error line. Or add a system prompt rule: "When a command fails, read the error output carefully. Identify: 1) which file has the error, 2) what line number, 3) what the error is. Then fix that specific issue."

---

## No Session Memory Within a Task

**Issue:** In a long session, the agent re-reads files it just created, re-searches for things it just found, and sometimes contradicts its own earlier edits. Each message is processed without awareness of what happened 10 messages ago.

**Examples:**
- Build 2: Agent created database.ts then later tried to import from it with the wrong path — didn't remember what it had created
- Both builds: Agent reads the same file multiple times across edits

**Occurrences:** Both builds — becomes worse as instruction complexity increases

**Root cause:** LangGraph state only holds messages. The agent has no structured memory of "files I created", "paths I verified", "errors I encountered". It relies on re-reading the conversation history.

**Proposed fix:** Add a `working_context` to agent state that tracks: files created this session, files edited, errors encountered, resolved paths. The agent can reference this without re-reading. This is related to SPEC-02 (visible task tracker) and SPEC-05 (auto-memory).

---

## Package Manager / Workspace Hoisting Confusion

**Issue:** Agent doesn't understand npm workspaces hoisting. Installs packages in the wrong directory, or expects packages to be in `packages/api/node_modules` when they're hoisted to the root `node_modules/`.

**Examples:**
- Build 2: Agent ran `npm install` in subdirectory when the root workspace would have handled it
- Both builds: Confusion about where node_modules actually lives

**Occurrences:** Both builds

**Proposed fix:** System prompt rule: "In npm workspaces, packages are hoisted to the root node_modules. Run npm install from the project root, not from individual packages. To add a dependency to a specific package, use `npm install <pkg> -w packages/api`."

---

## No Awareness of Common Framework Patterns

**Issue:** The agent doesn't know standard patterns that any developer would know: Express needs `express.json()` middleware, Vite needs `index.html`, React Router v6 uses `Routes` not `Switch`, React entry needs `createRoot`. These are constant across all projects using these frameworks.

**Examples:**
- Both builds: Missing index.html for Vite
- Build 1: React Router v5 syntax
- Build 2: Didn't set up express.json() middleware initially

**Occurrences:** Both builds

**Root cause:** The LLM's training data includes both old and new patterns. Without explicit guidance, it may pick outdated or incomplete patterns.

**Proposed fix:** For Build 3, include a "tech stack cheat sheet" in the project context:
- Vite: always needs index.html with script type=module pointing to src/main.tsx
- React: createRoot(document.getElementById('root')!).render(<App />)
- React Router v6: BrowserRouter, Routes, Route (NOT Switch, NOT v5)
- Express: app.use(express.json()) for POST body parsing
- TypeScript: run with `npx tsx`, compile check with `npx tsc --noEmit`

---

## Agent Can't Ask Clarifying Questions

**Issue:** When an instruction is ambiguous, the agent guesses instead of asking. It has no mechanism to request clarification from the user mid-task.

**Examples:**
- Build 1 Instruction 4: Agent guessed MongoDB-style methods for sql.js — a question like "which database API should I use?" would have saved 3 interventions
- Both builds: Agent guessed file paths instead of asking "should this go in packages/web or web?"

**Occurrences:** Both builds

**Root cause:** The agent loop is fire-and-forget. There's no "ask user" tool or pause mechanism.

**Proposed fix (long-term):** Add an `ask_user` tool that pauses execution and sends a question via SSE. The user responds, and the agent continues. This is a significant architecture change but would prevent many wrong guesses.

---

## Recursion Limit Too Low for Complex Tasks

**Issue:** 25 messages (~12 LLM turns) is not enough for instructions that involve creating 3+ files with verification. The agent runs out of budget, especially when verification steps (running the server, compile checks) consume messages.

**Examples:**
- Build 2 Instruction 3: Created database.ts correctly but burned remaining messages trying to verify
- Build 2 Instruction 7: Created 2 of 3 pages before hitting limit
- Build 1: Multiple instructions hit the limit

**Occurrences:** Both builds — instructions 3 and 7 consistently

**Root cause:** The recursion limit is a safety mechanism against infinite loops, but it's too low for legitimate complex tasks. Increasing it risks runaway behavior.

**Proposed fix:** Instead of a flat limit, implement a smarter circuit breaker:
- Track "productive" messages (those that create/edit files) vs "unproductive" (retries, failed reads)
- Stop after N unproductive messages in a row, not after N total messages
- Or: increase limit to 50 but add a "no progress for 10 messages" check

---

## Context Lost on Auto-Continue Iterations

**Issue:** When context files are attached via the `-c` flag, they are injected into the first instruction only. On auto-continue iterations, the continue message references the original instruction but does NOT re-inject the full context file contents. The agent then tries to find the documents on disk but fails.

**Examples:**
- Build 7: Agent received 4 context files (SHIP-PRD.md, DATA-MODELS.md, SPECS.md, WIREFRAMES.md) and used them successfully for Specs 1-2. On auto-continue iteration 2+, it searched for `DATA-MODELS.md` via `search_files` — not found because files are in `.shipyard/specs/` and the search didn't look there. Burned all 10 iterations searching.

**Occurrences:** Build 7 (Ship rebuild) — first autonomous single-prompt build with context files

**Root cause:** `_build_continue_message()` in `supervisor.py` constructs the continue message from the original instruction text (truncated to 500 chars) + progress.md content. It does NOT include the original context file contents. The context is in the first message of the first iteration's conversation but not persisted to subsequent iterations.

**Proposed fix (short-term):**
1. System prompt rule: "Planning documents and specs are ALWAYS in `.shipyard/specs/` or `.shipyard/notes/`. When you need reference material, check these directories first."
2. Copy spec files to project root so `search_files` finds them at top level.

**Proposed fix (long-term):**
1. Modify `_build_continue_message()` to re-inject context files from the original instruction.
2. Store attached context in `.shipyard/context/` on first iteration so it's discoverable on disk for subsequent iterations.
3. Add context file paths to the continue message: "Reference documents available at: .shipyard/specs/SHIP-PRD.md, .shipyard/specs/DATA-MODELS.md, etc."

**Severity:** CRITICAL — this completely blocks autonomous multi-spec builds with context injection.

---

## Agent Ignores Pinned Dependency Versions

**Issue:** The PRD specifies exact package versions (e.g., `express@4.21.2`, `react@18.3.1`) but the agent installs latest versions instead. This causes compatibility issues and breaks assumptions in the spec documents.

**Examples:**
- Build 7: PRD specifies `express@4.21.2`, agent installed `express@5.2.1` (major version jump, different API)
- Build 7: PRD specifies `react@18.3.1`, agent installed `react@19.2.4`
- Build 7: PRD specifies `tailwindcss@3.4.17`, agent installed `tailwindcss@4.2.2` (different config format)
- Build 7: PRD specifies `typescript@5.7.2`, agent installed `typescript@6.0.2`

**Occurrences:** Build 7 — all packages

**Root cause:** Agent runs `npm install <package>` without version specifiers. npm defaults to latest. The agent reads the version table in the PRD but doesn't use the versions when running install commands.

**Proposed fix:**
1. System prompt rule: "When the PRD or spec specifies package versions, install EXACT versions: `npm install express@4.21.2` not `npm install express`. Always include the @version suffix."
2. Include install commands with versions directly in the spec files so the agent can copy-paste them.
3. Provide a pre-built package.json in the specs so the agent can create it directly rather than running npm install commands.

**Severity:** HIGH — wrong major versions cause cascading failures (Express 5 has different middleware API, React 19 has different rendering, Tailwind 4 has different config).

---

## Agent Search Doesn't Find Files in Subdirectories

**Issue:** When the agent uses `search_files` to find a document, it searches the project root but doesn't find files nested in subdirectories like `.shipyard/specs/`. The agent doesn't try recursive search or alternative directory paths.

**Examples:**
- Build 7: Agent searched for "DATA-MODELS" and "SPECS.md" — returned no results. Files existed at `.shipyard/specs/DATA-MODELS.md` and `.shipyard/specs/SPECS.md`.
- Agent tried `search_files(pattern="DATA-MODELS")`, `search_files(pattern="SPECS.md")`, `list_files(depth=2)` — none found the `.shipyard/specs/` directory contents.

**Occurrences:** Build 7 — iterations 2-10 (all blocked on this)

**Root cause:** `list_files` skips `.shipyard/` directory by default (it's in the excluded directories list alongside `.git` and `node_modules`). `search_files` similarly doesn't search hidden/excluded directories. The agent has no way to discover files in `.shipyard/` without explicitly knowing to look there.

**Proposed fix:**
1. Don't put spec files in `.shipyard/` — put them in a visible directory like `docs/` or `specs/` at project root.
2. Modify `list_files` to include `.shipyard/specs/` in its output (exclude `.shipyard/sessions/` but show `.shipyard/notes/` and `.shipyard/specs/`).
3. System prompt rule: "Reference documents may be in `.shipyard/specs/`, `docs/`, or the project root. Check all three locations."

**Severity:** HIGH — agent can't access its own planning documents.

---

## Template

Copy this for new entries:

```
## [Short Title]

**Issue:** [What goes wrong]

**Examples:**
- [Specific instance]

**Occurrences:** [When/where it happened]

**Root cause:** [Why it happens]

**Proposed fix:** [System prompt rule, tool change, or architecture fix]
```
