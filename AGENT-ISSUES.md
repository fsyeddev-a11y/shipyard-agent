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
