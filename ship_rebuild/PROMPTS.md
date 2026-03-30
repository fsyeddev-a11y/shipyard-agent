# PROMPTS.md — Ship Rebuild Agent Prompts

Run these in order. Each prompt is a single `shipyard` CLI invocation.
The agent's project root should be set to the target directory (e.g., `~/ship-rebuild/`).

**Prerequisites:**
- PostgreSQL running locally
- `DATABASE_URL` env var set (e.g., `postgres://postgres:postgres@localhost:5432/ship`)
- Create the database: `createdb ship`

---

## Prompt 1: Scaffolding + Database + Shared Types (Specs 1-3)

```bash
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/DATA-MODELS.md -c ship_rebuild/SPECS.md "Read the attached PRD, DATA-MODELS, and SPECS documents. Implement Specs 1, 2, and 3 in order:

Spec 1: Create the monorepo scaffolding — root package.json with workspaces, packages/api, packages/web, packages/shared. Install ALL dependencies listed in the PRD Tech Stack section with exact versions. Set up Vite config with /api proxy to localhost:3001. Set up Tailwind with dark mode. Create index.html with div#root.

Spec 2: Create packages/shared/src/types.ts with ALL TypeScript types from the SPECS doc — DocumentType, IssueStatus, IssuePriority, User, Document, and all property interfaces (WikiProperties, ProgramProperties, ProjectProperties, IssueProperties, WeekProperties, DocumentAssociation).

Spec 3: Create packages/api/src/db/pool.ts (pg Pool from DATABASE_URL), packages/api/src/db/schema.sql (ALL tables from DATA-MODELS.md — users, sessions, documents, document_associations with all indexes), and packages/api/src/db/setup.ts that executes the schema SQL.

Run the setup script to create the tables. Verify npm install succeeds, TypeScript compiles, and tables exist."
```

---

## Prompt 2: Auth + API Shell (Specs 4, 13)

```bash
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/DATA-MODELS.md -c ship_rebuild/SPECS.md "Read the attached docs. Implement Specs 4 and 13:

Spec 4 — Auth: Create packages/api/src/app.ts with the Express app (middleware order: express.json, cookieParser, cors with credentials for localhost:5173, express-session, authMiddleware). Create packages/api/src/middleware/auth.ts that validates session cookie on every request except /api/auth/login and /api/health. Create packages/api/src/routes/auth.ts with POST /api/auth/login (bcrypt verify, create session row, set cookie), POST /api/auth/logout (delete session, clear cookie), GET /api/auth/me (return current user from session). Create packages/api/src/index.ts that starts the HTTP server on PORT 3001.

Spec 13 — Seed Data: Create packages/api/src/db/seed.ts that inserts 2 users (alice@ship.dev / password123, bob@ship.dev / password123 — bcrypt hashed), 3 wikis, 2 programs, 3 projects, 9 issues (3 per project with varied statuses/priorities/assignees/weeks), 12 week documents (4 per project), and all document_associations. Run the seed script.

Verify: Start the server, curl POST /api/auth/login with alice@ship.dev, confirm cookie is set, curl GET /api/auth/me returns user, curl without cookie returns 401."
```

---

## Prompt 3: Documents CRUD API (Spec 5)

```bash
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/DATA-MODELS.md -c ship_rebuild/SPECS.md "Read the attached docs. Implement Spec 5 — Documents CRUD:

Create packages/api/src/routes/documents.ts with:
- GET /api/documents — list documents, filter by ?type= query param, exclude deleted (deleted_at IS NULL)
- GET /api/documents/:id — fetch single document with its associations
- POST /api/documents — create document (generate UUID, set created_by from session user, create document_associations if associations array provided in body)
- PATCH /api/documents/:id — partial update (only fields in body), update updated_at
- DELETE /api/documents/:id — soft delete (set deleted_at = NOW())

Create packages/api/src/routes/index.ts that mounts all route files on the Express app.

Verify: Start server, create a wiki via curl POST, list wikis via GET ?type=wiki, update title via PATCH, delete via DELETE, confirm deleted doc not in list."
```

---

## Prompt 4: Frontend Shell (Spec 6)

```bash
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "Read the attached PRD, WIREFRAMES, and SPECS. Implement Spec 6 — Frontend Shell:

Create packages/web/src/lib/api.ts — fetch wrapper that includes credentials:'include', prepends /api, handles JSON responses and errors.

Create packages/web/src/contexts/AuthContext.tsx — React context with login(email, password), logout(), user state, loading state. On mount, call GET /api/auth/me to check existing session.

Create packages/web/src/pages/Login.tsx — centered card on gray-950 bg, email + password inputs, blue Login button, error message display. On success, redirect to /.

Create packages/web/src/components/Sidebar.tsx — fixed left 240px, gray-900 bg, nav links (Dashboard, Wiki, Programs, Projects, Teams), active link highlighted in blue-600, user avatar+initials at bottom, Settings link.

Create packages/web/src/components/Layout.tsx — Sidebar + main content area (children), gray-950 bg.

Update packages/web/src/App.tsx — React Router Routes with lazy-loaded pages. Unauthenticated → redirect to /login. Authenticated → Layout wrapper.

Update packages/web/src/main.tsx — QueryClientProvider, AuthProvider, BrowserRouter, App.

Verify: Web loads at localhost:5173, shows login page, login with alice@ship.dev/password123, see sidebar with navigation links, user initials at bottom."
```

---

## Prompt 5: Wiki End-to-End (Spec 7)

```bash
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "Read the attached WIREFRAMES and SPECS. Implement Spec 7 — Wiki pages:

Create packages/web/src/pages/WikiList.tsx — table showing all wiki documents (title, created date, updated date). '+ New Wiki' button in header. Click row navigates to /wiki/:id. Use React Query to fetch GET /api/documents?type=wiki.

Create packages/web/src/pages/WikiView.tsx — left content area (70%) showing title + body, right metadata sidebar (30%, gray-800 bg) showing Creator name, Created date, Updated date, Maintainer. Edit button toggles inline editing. Delete button shows confirmation modal.

Create packages/web/src/components/CreateDocumentModal.tsx — reusable modal with title + body fields. Props: documentType, onCreated, onClose. Posts to /api/documents.

Create packages/web/src/components/DeleteConfirmModal.tsx — reusable confirmation dialog. Props: title, onConfirm, onClose. Calls DELETE /api/documents/:id.

Add routes: /wiki → WikiList, /wiki/:id → WikiView.

Follow the dark theme from WIREFRAMES.md — gray-950 bg, gray-900 cards, gray-100 text, blue-600 buttons.

Verify: Navigate to /wiki, see 3 seeded wikis, create new wiki, click into it, edit title+body, delete it."
```

---

## Prompt 6: Programs End-to-End (Spec 8)

```bash
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md -c ship_rebuild/DATA-MODELS.md "Read the attached docs. Implement Spec 8 — Programs:

Backend: Create packages/api/src/routes/programs.ts with GET /api/programs (include project count via subquery on document_associations), GET /api/programs/:id, POST, PATCH, DELETE.

Frontend: Create packages/web/src/pages/ProgramsList.tsx — table with title, owner name, project count, updated date. '+ New Program' button.

Create packages/web/src/pages/ProgramView.tsx — tabbed view with 4 tabs: Overview, Issues, Projects, Weeks.
- Overview tab: program body, owner, approver, consulted, informed, dates. Edit/Delete buttons.
- Issues tab: fetch all issues in this program (through projects via document_associations). Table with title, status, priority, project name, updated.
- Projects tab: fetch projects in this program. Table with title, owner, issue count, ICE score, updated.
- Weeks tab: placeholder for now.

Each tab is a sub-component. Use URL search params or state for active tab. Status badges should be colored (green=done, blue=in_progress, yellow=in_review, gray=backlog, red=cancelled).

Add routes: /programs → ProgramsList, /programs/:id → ProgramView.

Verify: See 2 programs, click Platform, Overview shows details, Issues tab shows issues from Auth Redesign + API Gateway, Projects tab shows 2 projects. Create/edit/delete work."
```

---

## Prompt 7: Projects End-to-End (Spec 9)

```bash
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md -c ship_rebuild/DATA-MODELS.md "Read the attached docs. Implement Spec 9 — Projects:

Backend: Create packages/api/src/routes/projects.ts with GET /api/projects (include issue count, program name via joins), GET /api/projects/:id, POST (create project + program association), PATCH, DELETE.

Frontend: Create packages/web/src/pages/ProjectsList.tsx — table with title, owner, issue count, ICE score, program name.

Create packages/web/src/pages/ProjectView.tsx — tabbed view with 4 tabs: Overview, Issues, Weeks, Retro.
- Overview: body, ICE scores (impact/confidence/ease displayed as numbers, ice_score computed), owner, program link, design_approved badge. Edit/Delete.
- Issues: all issues in this project. Table with title, status, priority, assignee, week. '+ New Issue' button using CreateDocumentModal with issue-specific fields (status, priority, assignee dropdown, week number).
- Weeks: issues grouped by week_number. Each week shown as a section header ('Week N') with its issues listed below. Current week (highest number with issues) labeled 'Current'.
- Retro: placeholder text 'Coming soon'.

ICE score = (impact * confidence * ease) / 1.25. Recalculate on edit.

Add routes: /projects → ProjectsList, /projects/:id → ProjectView.

Verify: See 3 projects, click Auth Redesign, see ICE scores, Issues tab shows 3 issues, Weeks tab groups by week, create new issue with week assignment, it appears in Weeks tab."
```

---

## Prompt 8: Issues End-to-End (Spec 10)

```bash
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "Read the attached docs. Implement Spec 10 — Issues:

Backend: Create packages/api/src/routes/issues.ts with GET /api/issues (filterable by project_id, program_id, status, assignee_id via query params), GET /api/issues/:id (include project + program names via associations), PATCH /api/issues/:id (update any property — status, priority, assignee_id, week_number, title, body).

Frontend: Create packages/web/src/pages/IssueView.tsx — split layout per WIREFRAMES.md:
- Left (70%): title (editable), body (editable), Edit/Delete buttons
- Right metadata sidebar (30%, gray-800): Status dropdown (all 7 statuses), Priority dropdown (5 levels), Assignee dropdown (users list), Time estimate input, Week number input, Project name (link), Program name (link), Created date, Updated date

Status and priority dropdowns save immediately on change (PATCH call). Use colored badges: StatusBadge and PriorityBadge components.

Create packages/web/src/components/StatusBadge.tsx — colored badge (green=done, blue=in_progress, yellow=in_review, gray=backlog/todo/needs_triage, red=cancelled/urgent).
Create packages/web/src/components/PriorityBadge.tsx — priority indicator.

Add route: /issues/:id → IssueView.

Verify: Click an issue from any list, see full view with metadata sidebar, change status dropdown — saves and badge color changes, change assignee, assign to week, edit title+body, delete."
```

---

## Prompt 9: Dashboard + Final Polish (Specs 11, 12)

```bash
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "Read the attached docs. Implement Specs 11 and 12:

Spec 11 — Dashboard: Create packages/api/src/routes/dashboard.ts with GET /api/dashboard that returns issues assigned to the current session user where week_number equals the highest week_number that has assigned issues (current sprint).

Create packages/web/src/pages/Dashboard.tsx — 'My Current Sprint' header, table showing issue title, status badge, priority badge, week number. Click row navigates to /issues/:id.

Spec 12 — Teams: Create packages/api/src/routes/users.ts with GET /api/users (list all users).

Create packages/web/src/pages/Teams.tsx — table with display_name, email columns.

Add routes: / → Dashboard, /teams → Teams.

Verify: Login as Alice, dashboard shows only Alice's issues in current week, click issue navigates to detail. /teams shows Alice and Bob."
```

---

## Prompt 10: Full Verification (Spec 14)

```bash
shipyard -c ship_rebuild/SPECS.md "Run the full Spec 14 verification checklist:

1. Start the API server (background) and verify /api/health returns 200
2. Start the web dev server and verify it loads
3. Verify login works for alice@ship.dev
4. Verify Dashboard shows Alice's current sprint issues
5. Navigate to /wiki — verify 3 wikis show, create one, edit it, delete it
6. Navigate to /programs — verify 2 programs, click Platform, check all 4 tabs (Overview shows body, Issues shows issues from both projects, Projects shows 2 projects)
7. Navigate to /projects — verify 3 projects, click Auth Redesign, check Overview ICE scores, Issues tab, Weeks tab (grouped by week)
8. Create a new issue from a project, assign to a week, verify it appears in Weeks tab
9. Open an issue, change status/priority/assignee, verify saves persist
10. Login as Bob, verify dashboard shows Bob's issues
11. Verify all sidebar navigation works and active state highlights correctly

Write results to .shipyard/notes/progress.md with STATUS: COMPLETE if all pass."
```

---

## Quick Reference: Run Sequence

```bash
# 1. Scaffolding + DB + Types
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/DATA-MODELS.md -c ship_rebuild/SPECS.md "..."

# 2. Auth + Seed
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/DATA-MODELS.md -c ship_rebuild/SPECS.md "..."

# 3. Documents CRUD
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/DATA-MODELS.md -c ship_rebuild/SPECS.md "..."

# 4. Frontend Shell
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "..."

# 5. Wiki E2E
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "..."

# 6. Programs E2E
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md -c ship_rebuild/DATA-MODELS.md "..."

# 7. Projects E2E
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md -c ship_rebuild/DATA-MODELS.md "..."

# 8. Issues E2E
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "..."

# 9. Dashboard + Teams
shipyard -c ship_rebuild/WIREFRAMES.md -c ship_rebuild/SPECS.md "..."

# 10. Full Verification
shipyard -c ship_rebuild/SPECS.md "..."
```

**Alternatively, single-prompt autonomous build:**

```bash
shipyard -c ship_rebuild/SHIP-PRD.md -c ship_rebuild/DATA-MODELS.md -c ship_rebuild/SPECS.md -c ship_rebuild/WIREFRAMES.md "Read ALL attached documents. This is the Ship app rebuild PRD. Implement all 14 specs in order as defined in SPECS.md. Each spec has dependencies — follow the order exactly. Use DATA-MODELS.md for the database schema, WIREFRAMES.md for page layouts, and SHIP-PRD.md for tech stack versions and API endpoints. Write your plan to notes, then implement spec by spec. Verify each spec before moving to the next."
```
