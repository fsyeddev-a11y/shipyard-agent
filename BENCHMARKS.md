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
