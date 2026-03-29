# BENCHMARKS.md — Agent Performance Tracking

Track every test run and build. After each iteration, record what happened, what broke, what we fixed, and how performance changed. This is the raw data for the comparative analysis at final submission.

---

## Test Suite 1: Agent Capabilities (demo1)

**Date:** 2026-03-26
**Project:** demo1 — small TypeScript codebase (4 files, ~160 lines)
**Server:** Single persistent session for all 6 tests (no restart)
**Model:** gpt-4o

### Test 1: Surgical Edit (cross-file soft-delete)

**Prompt:** "Change the deleteUser function in src/users.ts to soft-delete: instead of splicing the array, add a deletedAt: Date field to the User interface in types.ts and set it in deleteUser. The function should return the deleted user instead of boolean."

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Tool calls | ~6 (list_files, read_file x2, edit_file x2) |
| Git commits | 2 (types.ts, users.ts) |
| Files touched | 2 (types.ts, users.ts) |
| Files should touch | 2 |
| Interventions | 0 |

**Trace:** https://smith.langchain.com/public/9a1d7b59-78f2-42b1-93fc-826177bb8711/r

---

### Test 2: Search and Discovery

**Prompt:** "Find everywhere that getUserById is used across the codebase. Add a check in each location: if the user has a deletedAt field set, treat them as not found."

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Tool calls | ~8 (search_files, read_file x2, edit_file x2) |
| Git commits | 2 (projects.ts, tasks.ts) |
| Files touched | 2 |
| Files should touch | 2 |
| Interventions | 0 |

**Notes:** Agent correctly identified that users.ts (where getUserById is defined) didn't need the check — only consumers in projects.ts and tasks.ts were modified.

**Trace:** https://smith.langchain.com/public/276523cc-f95b-42ef-972b-1424f6978773/r

---

### Test 3: File Creation

**Prompt:** "Create a new file src/validators.ts with input validation functions: validateUserName (must be 2-50 chars, no special chars), validateProjectName (must be 3-100 chars), and validateTaskTitle (must be 1-200 chars). Each should return { valid: boolean, error?: string }."

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Tool calls | ~2 (create_file) |
| Git commits | 1 |
| Files touched | 1 |
| Interventions | 0 |

**Minor note:** Used `export {}` at bottom instead of `export function` declarations. Functionally equivalent but different from codebase style.

**Trace:** https://smith.langchain.com/public/7e12c9a8-b331-4e7f-9ed8-e31dfcfd5173/r

---

### Test 4: Context Injection

**Prompt:** "Add JSDoc comments to all exported functions in src/projects.ts following the style guide" with `-c /tmp/style-guide.txt` attached

**Style guide contents:**
- All functions must have JSDoc comments with @param and @returns
- Use explicit return types on all exported functions
- Error messages must be prefixed with [ModuleName]

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Tool calls | ~4 (read_file, edit_file_multi) |
| Git commits | 1 (single atomic commit via edit_file_multi) |
| Files touched | 1 |
| Interventions | 0 |

**Notes:** Agent applied both JSDoc conventions AND the [ModuleName] error prefix from the injected context. Proves context injection works — agent used the attached file to inform its edits.

**Trace:** https://smith.langchain.com/public/d30b19cb-2910-44bd-9777-093edf8abe0e/r

---

### Test 5: Error Handling

**Prompt:** "Update the processPayment function in src/billing.ts to add retry logic"

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Tool calls | ~4 (search_files x3, list_files) |
| Git commits | 0 |
| Files touched | 0 |
| Interventions | 0 |

**Notes:** Agent searched for the function, couldn't find it, and reported back clearly without touching any files. No hallucination.

**Trace:** https://smith.langchain.com/public/ca4b0de2-5e12-41a8-8808-730301b13e05/r

---

### Test 6: Run Command

**Prompt:** "List all TypeScript files in the project and count the total lines of code across all of them. Report the results."

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Tool calls | ~6 (list_files, read_file x5) |
| Git commits | 0 |
| Files touched | 0 |
| Interventions | 0 |

**Notes:** Agent read each file and calculated totals (206 lines across 5 files). Used read_file instead of run_command with `wc -l` — works but less efficient.

**Trace:** https://smith.langchain.com/public/4759d6bb-45b4-4862-a6a2-f5110e00226c/r

---

### Test Suite 1 Summary

| Metric | Value |
|--------|-------|
| Tests passed | 6/6 |
| Total interventions | 0 |
| Total tool calls | ~30 |
| Precision (correct files only) | 100% |

**Pre-test fix applied:** System prompt Rule 3 (don't include line numbers in anchors) and Rule 10 (stop when done). These were added after the first demo2 attempt where the agent wasted 5 attempts on line-number anchors and hit the recursion limit.

---

## Build 1: Helm — Full-Stack Project Management App

**Date:** 2026-03-27
**Project:** Helm — Express + SQLite + React + Vite + TailwindCSS monorepo
**Model:** gpt-4o
**PRD:** HELM-BUILD1.md (8 instructions)

### Instruction 1: Project Scaffolding

**Prompt:** Create monorepo with api, web, shared packages, configure workspaces, tsconfigs, Vite proxy.

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 1 |
| Issue | Agent used `packages/` directory (not in PRD but acceptable) |
| Issue | Dependencies not installed — `npm install` needed manually |

---

### Instruction 2: Shared Types

**Prompt:** Create Document, DocumentType, CreateDocumentInput, UpdateDocumentInput in shared/types.ts.

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 1 |
| Issue | Created `shared/` at root AND inside `packages/shared/` (duplicate) |
| Fix | Told agent to merge into packages/shared/ and delete root shared/ |

**Bug found:** File placement — agent doesn't check existing project structure before creating files.

---

### Instruction 3: Database Setup

**Prompt:** Set up SQLite with better-sqlite3, create documents table, seed data.

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 2 |
| Issue 1 | `better-sqlite3` failed to compile (native module, Apple Silicon + Node 20 incompatibility) |
| Fix 1 | Told agent to switch to `sql.js` (pure JS, no native compilation) |
| Issue 2 | Seed function crashed on restart — UNIQUE constraint on duplicate inserts |
| Fix 2 | Told agent to check if data exists before seeding |

**Note:** The better-sqlite3 failure is an environment issue, not an agent issue. The agent handled the switch to sql.js correctly when told.

---

### Instruction 4: API Routes

**Prompt:** CRUD routes for documents, error handling middleware, wire up in index.ts.

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 3 |
| Issue 1 | Import mismatch — routes imported `getDatabase()` which didn't exist in database.ts |
| Fix 1 | Told agent to fix import |
| Issue 2 | All routes returned "Something broke!" — error middleware hiding real errors |
| Fix 2 | Told agent to debug and fix |
| Issue 3 | Agent used MongoDB-style methods (`db.documents.findOne()`) in some routes even though database is sql.js |
| Fix 3 | Told agent to rewrite all routes using sql.js API |

**Verified:** After fixes, `curl` returned correct JSON objects with camelCase field names.

---

### Instruction 5: API Client

**Prompt:** Create fetch wrapper in web/src/api/client.ts.

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 1 |
| Issue | Used `new URL('/api/documents')` which requires a full base URL — fails in browser |
| Fix | Told agent to use string concatenation instead of URL constructor |

---

### Instruction 6: Layout and Components

**Prompt:** Create Layout, DocumentCard, CreateDocumentForm components with TailwindCSS.

| Metric | Value |
|--------|-------|
| Pass | Fail |
| Interventions | 2 |
| Issue 1 | Created `web/` at root instead of `packages/web/` (duplicate structure again) |
| Fix 1 | Told agent to move files into packages/web/ |
| Issue 2 | All 3 components were missing — agent created page files instead |
| Fix 2 | Sent separate prompt to create Layout, DocumentCard, CreateDocumentForm |

**Bug found:** Recurring file placement issue + agent confused components with pages.

---

### Instruction 7: Pages and Routing

**Prompt:** Set up React Router, create WorkspacePage, ProgramPage, ProjectPage.

| Metric | Value |
|--------|-------|
| Pass | Fail (initially) |
| Interventions | 6 |
| Issue 1 | Pages created in `components/` instead of `pages/` |
| Issue 2 | `index.html` missing — Vite can't serve anything |
| Issue 3 | `main.tsx` missing |
| Issue 4 | React Router v5 syntax (Switch) used instead of v6 (Routes) |
| Issue 5 | `react-router-dom` not installed |
| Issue 6 | TailwindCSS not configured, `index.css` missing |
| Issue 7 | Page files were empty (0 bytes) after move attempt |

**Fixes applied:**
- Told agent to create index.html and main.tsx
- Told agent to fix React Router v5→v6
- Manually installed react-router-dom
- Told agent to create index.css with Tailwind directives
- Sent 4 separate prompts to write each page component individually
- Told agent to add Link import for ProgramPage

---

### Instruction 8: Polish and Verify

**Status:** Not sent as a single instruction. Debugging was done incrementally through instructions 5-7 fixes.

**Final result after all fixes:**
- Workspace page loads with "Engineering" and two programs (Platform, Product) ✓
- Clicking a program navigates to program page with projects ✓
- Clicking a project navigates to project page with issues ✓
- Create document form present on each page ✓
- Breadcrumb navigation works ✓
- Issues show with status (open/closed) ✓

**Not working:**
- TailwindCSS not applied (no styled badges, no grid layout)
- Breadcrumb on project page shows "Workspace / /" (missing program name)
- Status concatenated with title instead of separate badge ("Platform Issue 1open")

---

### Build 1 Summary

| Metric | Value |
|--------|-------|
| Instructions | 8 planned, 7 sent + ~15 fix prompts |
| Total interventions | ~16 |
| Total prompts sent | ~22 |
| Backend working | ✓ (after 6 interventions) |
| Frontend working | ✓ (after 10 interventions) |
| End-to-end data flow | ✓ |
| Styling | ✗ (Tailwind not applied) |

### Recurring Issues Found

| Issue | Occurrences | Planned Fix |
|-------|-------------|-------------|
| Files created in wrong location | 3 (Instructions 2, 6, 7) | System prompt: check project structure before creating files |
| Dependencies not installed | 3 (Instructions 1, 3, 7) | System prompt: install packages when creating files that import them |
| Missing essential framework files | 2 (Instructions 1, 7) | System prompt: create all required entry points for frameworks |
| Agent loops on same failing edit | 1 (cleanup prompt) | Better error messages + system prompt retry rule |
| Mixed API styles (MongoDB on sql.js) | 1 (Instruction 4) | N/A — one-off confusion |
| React Router v5/v6 confusion | 1 (Instruction 7) | System prompt: use latest version of frameworks |
| Empty anchor infinite loop | 1 (cleanup prompt) | ✓ Fixed — engine rejects empty anchors |

### Cost

| Metric | Value |
|--------|-------|
| Sessions | ~22 |
| LLM calls | ~50-60 (estimated) |
| Estimated cost | < $1.00 |

---

## Planned Improvements (Pre-Build 2)

### System Prompt Updates
1. **File placement rule:** "Before creating any file, run list_files to understand the project structure. Place files relative to existing directories."
2. **Dependency rule:** "When creating files that import external packages, run npm install (or equivalent) in the same instruction."
3. **Framework rule:** "When scaffolding a framework (React+Vite, Express, etc.), always create ALL required entry points even if not explicitly listed."
4. **Retry rule:** "If an edit fails twice with the same error, change your approach — do not retry the same edit."
5. **Version rule:** "Use the latest stable version of frameworks and libraries. React Router v6 not v5."

### Tool Improvements
1. Add `move_file` tool
2. Add `delete_file` tool
3. Improve edit engine error messages with actionable guidance

### Engine Fixes
1. ✓ Empty anchor guard (already fixed)
2. Better error messages for verification failures

---

## Build 2: Helm v2 — Same PRD, Improved Agent

**Date:** 2026-03-27
**Project:** helm-v2 — same HELM-BUILD1.md PRD as Build 1
**Model:** gpt-4o
**Changes since Build 1:** System prompt overhaul (19 rules), move_file/delete_file tools, improved error messages

### Instruction 1: Project Scaffolding

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Interventions | 0 |

**Improvement over Build 1:** Agent installed dependencies, created main.tsx and index.css, used packages/ structure. Planning step visible in output. No manual npm install needed for this step.

---

### Instruction 2: Shared Types

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 1 |
| Issue | Created `shared/types.ts` at root instead of `packages/shared/types.ts` |
| Fix | Told agent to move file to packages/shared/ |

**Same issue as Build 1.** The prompt says "shared/types.ts" and the agent creates it literally. The system prompt rule about checking project structure was followed (agent ran list_files and saw packages/) but still didn't connect "shared" → "packages/shared".

---

### Instruction 3: Database Setup

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 1 |
| Issue | Agent tried to verify by running `npm start` — hit 60s timeout. Then tried `node`, `tsc`, `npm install -g typescript` — all failed. Hit recursion limit. |
| Fix | Manually installed tsx, ran server with `npx tsx` |

**New issue:** The "verify after creating" system prompt rule backfired — the agent correctly tried to test but doesn't know how to run TypeScript or handle long-running servers. Used up entire message budget on verification attempts.

**Dependency issue:** Agent installed `sql.js` but not `tsx`, `@types/express`, or `@types/node`. Partial dependency installation persists.

---

### Instruction 4: API Routes

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 2 |
| Issue 1 | Missing `uuid` and `@types/uuid` — had to manually install |
| Issue 2 | `db` variable referenced outside its scope — createDocumentsRouter(db) was outside the .then() callback |
| Issue 3 | sql.js results returned as arrays instead of objects (same as Build 1) |
| Fix 1 | Manual `npm install uuid @types/uuid` |
| Fix 2 | Told agent to move router init inside the .then() block |
| Fix 3 | Told agent to map sql.js results to camelCase objects |

**Recurring issues:** Dependency gaps and sql.js array→object mapping both repeated from Build 1.

---

### Instruction 5: API Client

| Metric | Value |
|--------|-------|
| Pass | ✓ |
| Interventions | 0 |

---

### Instruction 6: Layout and Components

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 1 |
| Issue | Created `web/src/components/` at root instead of `packages/web/src/components/` |
| Fix | Told agent to use move_file to relocate and rm -rf root web/ |

**Same recurring file placement issue.** Agent ran list_files, saw packages/, but still created files at root.

---

### Instruction 7: Pages and Routing

| Metric | Value |
|--------|-------|
| Pass | Partial |
| Interventions | 4 |
| Issue 1 | Hit recursion limit — created 2 of 3 pages before running out |
| Issue 2 | `index.html` missing (same as Build 1) |
| Issue 3 | Duplicate App declaration in main.tsx (import + inline const) |
| Issue 4 | Double BrowserRouter (one in main.tsx, one in App.tsx) |
| Fix 1 | Sent follow-up prompt for ProjectPage |
| Fix 2 | Told agent to create index.html |
| Fix 3 | Told agent to remove duplicate App definition |
| Fix 4 | Told agent to remove BrowserRouter from main.tsx |

**Missing index.html persists** despite system prompt rule about framework entry points. Pages placed in components/ instead of pages/ (noted but didn't fix — not blocking).

---

### Build 2 Summary

| Metric | Build 1 | Build 2 | Change |
|--------|---------|---------|--------|
| Interventions | 16 | 9 | -44% |
| Total prompts | ~22 | ~15 | -32% |
| Backend working | ✓ (6 fixes) | ✓ (3 fixes) | -50% backend issues |
| Frontend working | ✓ (10 fixes) | ✓ (6 fixes) | -40% frontend issues |
| Agent planned before coding | No | Yes | New behavior |
| Agent attempted verification | No | Yes | New behavior (but caused timeouts) |
| Styling | ✗ | ✗ | Same |

### Recurring Issues Still Present

| Issue | Build 1 | Build 2 | Status |
|-------|---------|---------|--------|
| Files at wrong location (root vs packages/) | 3 occurrences | 3 occurrences | **Not fixed** — system prompt rule too weak |
| Missing dependencies (@types/*, peer deps) | 3 occurrences | 2 occurrences | Slightly better but not fixed |
| Missing index.html | 1 occurrence | 1 occurrence | **Not fixed** — system prompt rule not followed |
| sql.js arrays not mapped to objects | 1 occurrence | 1 occurrence | **Not fixed** — agent doesn't know sql.js format |
| Server timeout on verification | Hidden (didn't try) | 2 occurrences | **New** — caused by vertical dev rule |

### New Issues Found in Build 2

| Issue | Impact |
|-------|--------|
| Agent can't run TypeScript (doesn't know about tsx) | Blocks verification, wastes messages |
| Server verification hits 60s timeout, burns message budget | Agent follows "verify" rule but can't handle long-running processes |
| Duplicate code in main.tsx (import + inline definition) | Agent edits append instead of replace |

### Key Insight: File Placement Root Cause

The file placement issue persists because the agent interprets instruction paths literally. When the prompt says "web/src/components/", the agent creates exactly that path — it doesn't resolve "web" to "packages/web" even though it can see packages/ in the file listing.

**Proposed fix for Build 3:** Before sending any build instructions, send an initial "project context" prompt that tells the agent the project hierarchy:

```
"This is a monorepo. The project structure is:
- packages/api/ — Express backend
- packages/web/ — React frontend
- packages/shared/ — shared TypeScript types
When instructions reference api, web, or shared, always use the packages/ prefix."
```

This front-loads the context instead of relying on the agent to infer it from list_files.

---

## Comparison: Build 1 → Build 2

```
Interventions:        16 → 9  (-44%)
Prompts sent:         22 → 15 (-32%)
Issues resolved:      3 (empty anchor, line numbers in anchors, post-completion rambling)
Issues persisting:    4 (file placement, deps, index.html, sql.js mapping)
New issues:           2 (server timeout, can't run TypeScript)
```

The system prompt overhaul worked for **behavioral** issues (planning, vertical development) but failed for **knowledge** issues (where files go in monorepos, what sql.js returns, how to run TypeScript). Knowledge issues may need either:
1. Project-specific context injection (tell the agent about the project before starting)
2. Domain-specific system prompt rules (TypeScript/React/monorepo patterns)
3. Learning from errors within a session (auto-memory, SPEC-05)

---

## Planned Improvements (Pre-Build 3)

### Project Context Injection
- Before Build 3, send a "project context" prompt establishing the monorepo structure
- Tell the agent explicitly: api = packages/api, web = packages/web, shared = packages/shared
- This addresses the #1 recurring issue (file placement)

### TypeScript Execution Knowledge
- System prompt rule: "To run TypeScript, use npx tsx. Install tsx as dev dep first."
- System prompt rule: "When installing npm packages for TypeScript, always install @types/* too."

### Server Verification Strategy
- System prompt rule: "To test a server, start it in background: `npx tsx src/index.ts &`, then curl, then kill %1. Or use `timeout 5 npx tsx src/index.ts` to check it doesn't crash."
- Long-term: implement background process support (SPEC-04)

### sql.js Knowledge
- System prompt rule or project context: "sql.js db.exec() returns {columns, values} arrays. Always map to objects."

---

## Build 3 / 3.2: Helm — Autonomous Single-Prompt Build

**Date:** 2026-03-27
**Project:** helm-v3 / helm-v3.2 — same HELM-BUILD1.md PRD, rewritten for autonomous execution
**Model:** gpt-4o

### Changes Since Build 2

**System prompt v4→v5 (major overhaul):**
- PRD-Driven Workflow section: agent reads PRD, breaks into specs, writes plan to notes
- Progress Checkpoints (mandatory): write checkpoint at start and end of every spec
- Resume support: agent reads notes at session start, picks up where last session stopped
- Removed hardcoded `packages/` rule — replaced with discovery-based path resolution

**New tools:**
- `write_note` and `read_notes` — agent self-tracks plan, progress, and issues in `.shipyard/notes/`
- Total tools: 11 (was 9)

**Smart circuit breaker (replaces flat 50-message limit):**
- Hard gate: 100 messages (~50 LLM turns). Absolute ceiling.
- Soft gate: 5 consecutive unproductive turns → stop. Productive = successful file create/edit/move/delete/write_note. Failed edits count as unproductive.
- LangGraph recursion_limit raised to 200 to match.
- Why: Build 2 hit the old 25-step LangGraph limit on every complex instruction. The agent could only do ~12 LLM turns total — not enough for multi-file work with verification. The new breaker allows ~50 productive turns while still catching infinite retry loops.

**PRD rewrite:**
- Path-free instructions — agent decides directory structure during planning phase
- sql.js explicitly specified (not better-sqlite3), with mapping requirements
- ASCII wireframes for all 3 pages with Tailwind classes
- 10-item verification checklist
- Agent writes plan/progress/issues to `.shipyard/notes/`

**CLI fix:**
- `-c` flag now works before or after the instruction text

### Build 3 (helm-v3) — First Attempt

Single prompt with PRD attached. Agent completed 6 of 8 specs before hitting old recursion limit:

| Spec | Status | Notes |
|------|--------|-------|
| 1. Monorepo scaffolding | ✓ | All files in packages/, correct structure |
| 2. Shared types | ✓ | |
| 3. Database (sql.js) | ✓ | |
| 4. API routes | ✓ | |
| 5. API client | ✓ | |
| 6. Components | ✓ | Layout, DocumentCard, CreateDocumentForm |
| 7. Pages + routing | ✗ | Hit recursion limit |
| 8. Verification | ✗ | Not reached |

**Key improvements over Build 2:**
- Agent wrote a full plan to `.shipyard/notes/plan.md` before coding
- Zero file placement issues — all files in correct directories
- Agent chose its own package names (backend/frontend/shared vs api/web/shared)
- 0 interventions for specs 1-6 (Build 2 needed 5 interventions for the same work)

**What went wrong:**
- Hit LangGraph's default 25-step recursion limit (our custom 50-message breaker wasn't the bottleneck — LangGraph's own limit was lower)
- No progress.md written — agent didn't checkpoint before running out of budget
- Follow-up prompts needed 2 more sessions to finish pages (each hit the limit again)

This triggered the smart circuit breaker implementation.

### Build 3.2 (helm-v3.2) — With Smart Circuit Breaker

**Status:** In progress. Testing with new 100-message hard limit and 5-turn unproductive soft limit.

*Results to be filled in after completion.*

---

## Build 4: Helm v4 — Auto-Continue Loop + Full Autonomous Build

**Date:** 2026-03-28
**Project:** helm-v4 — same HELM-BUILD1.md PRD
**Model:** gpt-4o

### Changes Since Build 3

**Auto-continue loop (run_agent_loop):**
- REPL-style outer loop that re-invokes run_agent() when STATUS: COMPLETE not found in progress.md
- Max 10 iterations, deterministic continue message (no extra LLM calls)
- Intermediate "done" events suppressed — CLI sees one final "Done"

**Status Protocol:**
- Agent must write STATUS: COMPLETE or STATUS: IN_PROGRESS to progress.md
- If omitted, system assumes IN_PROGRESS and re-runs (safe default)

**append_note tool:**
- Timestamped append to notes instead of overwrite
- Progress log preserves full history across iterations

**CLI status tracker:**
- Running counts after each tool result (iteration, tools, edits, created)
- Cyan auto-continue banner between iterations
- Green summary on completion

**System prompt fixes:**
- "Planning is NOT the end of the task" rule
- Progress uses append_note, not write_note

### Results

**Agent completed all 8 specs autonomously** — first time. Auto-continue loop worked, looping through iterations until verification phase.

| Spec | Status | Notes |
|------|--------|-------|
| 1. Monorepo scaffolding | ✓ | All files in packages/, correct structure |
| 2. Shared types | ✓ | |
| 3. Database (sql.js) | ✓ | Table created, but seed data incomplete |
| 4. API routes | ✓ | CRUD working, but sql.js null check missing |
| 5. API client | ✓ | Used full URL instead of /api (CORS issue) |
| 6. Components | ✓ | Layout, DocumentCard, CreateDocumentForm |
| 7. Pages + routing | ✓ | All 3 pages with data fetching |
| 8. Verification | Partial | Burned ~5 iterations on server timeout |

### Interventions

**Code interventions (agent should have handled these):**
1. API client used `http://localhost:3001/api` instead of `/api` → CORS error
2. sql.js `db.exec()` returns empty array but code assumed `.values` exists → 500 error
3. Seed function only inserted workspace, left `// Add more` comment for programs/projects/issues
4. React 17 installed instead of React 18 (`react-dom/client` doesn't exist in 17)

**Environment interventions (not the agent's fault):**
5. Port 3001 in use from agent's earlier timeout attempts → manual kill
6. Vite latest requires Node 20.19+ but system has 20.16 → pinned Vite 4.x
7. npm workspace hoisting prevented local package resolution → multiple reinstalls
8. Stale Vite zombie processes on ports 5173-5183 → manual kill

**Total interventions:** ~8 (4 code + 4 environment)

### Build 4 Summary

| Metric | Build 1 | Build 2 | Build 3 | Build 4 |
|--------|---------|---------|---------|---------|
| Interventions | 16 | 9 | N/A (incomplete) | 8 |
| Agent completed all specs | No | No | 6/8 | **8/8** |
| Auto-continue | N/A | N/A | N/A | **Yes** |
| File placement issues | 3 | 3 | 0 | **0** |
| End-to-end working | ✓ (16 fixes) | ✓ (9 fixes) | Not tested | **✓ (8 fixes)** |
| Plan written before coding | No | No | Yes | **Yes** |
| Progress tracked in notes | No | No | Yes (overwritten) | **Yes (append)** |

### Recurring Issues Across All Builds

| Issue | Build 1 | Build 2 | Build 4 | Root Cause |
|-------|---------|---------|---------|------------|
| sql.js array/null issues | ✓ | ✓ | ✓ | Agent doesn't know sql.js API despite system prompt |
| Server timeout burns iterations | Hidden | ✓ | ✓ | No background process support |
| Incomplete seed data | ✓ (double insert) | ✓ (double insert) | ✓ (missing data) | Agent leaves placeholders |
| Wrong dependency versions | N/A | N/A | ✓ (React 17, Vite 2) | LLM training data has old versions |
| CORS / wrong API base URL | N/A | N/A | ✓ | Agent ignores proxy setup |

### Key Insight

The remaining issues fall into two categories:

1. **Knowledge issues** (React 17 vs 18, Vite versions, sql.js API) — the LLM's training data is outdated. Fix: either pin versions in the PRD, or give the agent a tool to look up current stable versions.

2. **Environment issues** (Node version, port conflicts, workspace hoisting) — these are system-level problems the agent can't control. Fix: document system requirements, or containerize.

The core agent architecture (plan → implement → verify → auto-continue) is working. The next improvements should focus on giving the agent better tools and knowledge, not more system prompt rules.

---

## Comparison: Build 1 → Build 4

```
Interventions:        16 → 8  (-50%)
File placement:       3 errors → 0 errors (fixed)
Auto-continue:        manual → automated (new capability)
Specs completed:      manual per-spec → all 8 autonomous
Progress tracking:    none → timestamped append log
Plan before coding:   no → yes
End-to-end working:   yes (both builds, after fixes)
```

## Comparison Template (for final submission)

After each build iteration, fill in:

```
Build N vs Build N-1:
- Interventions: X → Y (change%)
- Prompts sent: X → Y
- Recurring issues resolved: [list]
- New issues found: [list]
- Cost: $X → $Y
```
