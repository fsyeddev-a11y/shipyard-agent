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

**Proposed fix:** System prompt rule: "Before creating any file, run list_files to understand the project structure. Place files relative to existing directories. If a packages/ or src/ directory already exists, create files inside it — never create a duplicate at the root."

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
