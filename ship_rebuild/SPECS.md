# SPECS.md — Ship App Implementation Specs

## How to Use This Document

Each spec is a **vertical slice** — it creates something end-to-end that can be verified independently. Implement specs **in order** (dependencies are explicit). Each spec lists:

- **What:** Files to create/edit
- **Depends on:** Which specs must be complete first
- **Verify:** How to confirm it works
- **User stories:** Which US-* items this covers

---

## Spec 1: Monorepo Scaffolding

**Depends on:** Nothing
**User stories:** None (infrastructure)

### What

Create the npm workspace monorepo with three packages.

### Files to Create

```
ship/
├── package.json                    # Root workspace config
├── tsconfig.json                   # Root TypeScript config (references)
├── packages/
│   ├── api/
│   │   ├── package.json            # Express + pg + dependencies
│   │   ├── tsconfig.json           # Node target, ESM
│   │   └── src/
│   │       └── index.ts            # "Hello" placeholder
│   ├── web/
│   │   ├── package.json            # React + Vite + dependencies
│   │   ├── tsconfig.json           # DOM target
│   │   ├── vite.config.ts          # Proxy /api → localhost:3001
│   │   ├── tailwind.config.js      # Dark mode class strategy
│   │   ├── postcss.config.js       # Tailwind + autoprefixer
│   │   ├── index.html              # Vite entry (div#root + script src=/src/main.tsx)
│   │   └── src/
│   │       ├── main.tsx            # createRoot + BrowserRouter + App
│   │       ├── App.tsx             # Routes wrapper (placeholder)
│   │       └── index.css           # Tailwind directives (@tailwind base/components/utilities)
│   └── shared/
│       ├── package.json
│       ├── tsconfig.json
│       └── src/
│           └── types.ts            # Document type enums + interfaces
```

### Root package.json
```json
{
  "name": "ship",
  "private": true,
  "workspaces": ["packages/*"]
}
```

### Key Dependencies to Install

**API (packages/api):**
```
express@4.21.2 pg@8.13.1 bcryptjs@3.0.3 uuid@11.0.3 express-session@1.18.1
cookie-parser@1.4.7 cors@2.8.5 zod@3.24.1
```
Dev: `@types/express@^5.0.0 @types/pg@^8.11.0 @types/bcryptjs@^2.4.0 @types/uuid@^10.0.0 @types/express-session@^1.18.0 @types/cookie-parser@^1.4.0 @types/cors@^2.8.0 tsx@4.19.2 typescript@5.7.2`

**Web (packages/web):**
```
react@18.3.1 react-dom@18.3.1 react-router-dom@7.1.1 @tanstack/react-query@5.62.0
```
Dev: `@types/react@^18.3.0 @types/react-dom@^18.3.0 vite@6.0.5 @vitejs/plugin-react@4.3.4 tailwindcss@3.4.17 autoprefixer@10.4.20 postcss@8.4.49 typescript@5.7.2`

### Verify
- `npm install` from root succeeds
- `npx tsx packages/api/src/index.ts` runs without error
- `npx vite --config packages/web/vite.config.ts` serves the web app

---

## Spec 2: Shared Types

**Depends on:** Spec 1
**User stories:** None (infrastructure)

### What

Define all TypeScript types in the shared package.

### File: packages/shared/src/types.ts

```typescript
// Document types
export type DocumentType = 'wiki' | 'issue' | 'program' | 'project' | 'week';

export type IssueStatus = 'needs_triage' | 'backlog' | 'todo' | 'in_progress' | 'in_review' | 'done' | 'cancelled';

export type IssuePriority = 'no_priority' | 'low' | 'medium' | 'high' | 'urgent';

export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  created_at: string;
  updated_at: string;
}

export interface Document {
  id: string;
  document_type: DocumentType;
  title: string;
  body: string;
  properties: Record<string, any>;
  created_by?: string;
  created_at: string;
  updated_at: string;
  deleted_at?: string;
}

export interface WikiProperties {
  maintainer_id?: string;
}

export interface ProgramProperties {
  owner_id?: string;
  approver_id?: string;
  consulted_id?: string;
  informed_id?: string;
}

export interface ProjectProperties {
  owner_id?: string;
  approver_id?: string;
  consulted_id?: string;
  informed_id?: string;
  program_id?: string;
  design_approved?: boolean;
  impact?: number;
  confidence?: number;
  ease?: number;
  ice_score?: number;
}

export interface IssueProperties {
  status: IssueStatus;
  priority: IssuePriority;
  assignee_id?: string;
  time_estimate?: number;
  project_id?: string;
  program_id?: string;
  week_number?: number;
}

export interface WeekProperties {
  week_number: number;
  project_id?: string;
}

export interface DocumentAssociation {
  id: string;
  document_id: string;
  related_id: string;
  relationship_type: string;
  created_at: string;
}
```

### Verify
- TypeScript compiles without errors: `npx tsc --noEmit -p packages/shared/tsconfig.json`

---

## Spec 3: Database Setup

**Depends on:** Spec 1
**User stories:** None (infrastructure)

### What

Create the PostgreSQL schema and a setup script.

### Files
- `packages/api/src/db/pool.ts` — pg Pool (from DATABASE_URL)
- `packages/api/src/db/schema.sql` — All CREATE TABLE statements
- `packages/api/src/db/setup.ts` — Reads schema.sql, executes against DB

### Verify
- `DATABASE_URL=postgres://... npx tsx packages/api/src/db/setup.ts` creates all tables
- Tables visible in psql: `\dt` shows users, sessions, documents, document_associations

---

## Spec 4: Auth — Users + Sessions + Login API

**Depends on:** Spec 3
**User stories:** US-AUTH-1, US-AUTH-2, US-AUTH-3

### What

Implement authentication: user creation, login, session management, auth middleware.

### Files
- `packages/api/src/middleware/auth.ts` — authMiddleware (validates session cookie)
- `packages/api/src/routes/auth.ts` — POST /login, POST /logout, GET /me
- `packages/api/src/app.ts` — Express app setup (middleware stack)
- `packages/api/src/index.ts` — HTTP server (listens on PORT || 3001)

### Middleware Order in app.ts
```
express.json()
cookieParser()
cors({ origin: 'http://localhost:5173', credentials: true })
session config (express-session with pg store or memory)
authMiddleware (except /api/auth/login, /api/health)
routes
```

### Verify
- Start server: `DATABASE_URL=... npx tsx packages/api/src/index.ts`
- `curl -X POST localhost:3001/api/auth/login -H 'Content-Type: application/json' -d '{"email":"alice@ship.dev","password":"password123"}'` returns user + sets cookie
- `curl localhost:3001/api/auth/me -b <cookie>` returns user
- `curl localhost:3001/api/auth/me` (no cookie) returns 401

---

## Spec 5: Documents CRUD API

**Depends on:** Spec 4
**User stories:** None directly (foundation for all document types)

### What

Implement the unified documents CRUD endpoints.

### Files
- `packages/api/src/routes/documents.ts` — GET /documents, GET /documents/:id, POST /documents, PATCH /documents/:id, DELETE /documents/:id
- `packages/api/src/routes/index.ts` — Route aggregator (mounts all route files on app)

### Key Behaviors
- GET /documents accepts `?type=wiki` query param to filter by document_type
- POST creates document + any document_associations passed in body
- PATCH updates only fields present in body
- DELETE sets deleted_at (soft delete)
- All queries exclude `WHERE deleted_at IS NULL`

### Verify
- `curl -X POST localhost:3001/api/documents -b <cookie> -H 'Content-Type: application/json' -d '{"document_type":"wiki","title":"Test"}'` → 201 with document
- `curl localhost:3001/api/documents?type=wiki -b <cookie>` → array with the wiki
- `curl -X PATCH localhost:3001/api/documents/<id> -b <cookie> -d '{"title":"Updated"}'` → updated doc
- `curl -X DELETE localhost:3001/api/documents/<id> -b <cookie>` → 204

---

## Spec 6: Frontend Shell — Layout, Sidebar, Router, Auth

**Depends on:** Spec 4, Spec 1
**User stories:** US-AUTH-1, US-AUTH-4, US-NAV-1, US-NAV-3

### What

Build the frontend shell: login page, auth context, sidebar layout, React Router setup.

### Files
- `packages/web/src/lib/api.ts` — Fetch wrapper (includes credentials, base URL)
- `packages/web/src/contexts/AuthContext.tsx` — Auth provider (login, logout, current user)
- `packages/web/src/components/Layout.tsx` — Sidebar + main content area
- `packages/web/src/components/Sidebar.tsx` — Navigation links with active state
- `packages/web/src/pages/Login.tsx` — Email + password form
- `packages/web/src/App.tsx` — Route definitions (lazy-loaded pages)
- `packages/web/src/main.tsx` — QueryClientProvider + AuthProvider + BrowserRouter + App

### Verify
- Web app loads at localhost:5173
- Login page renders at `/login`
- Entering correct credentials → redirects to `/` with sidebar
- Sidebar shows Dashboard, Wiki, Programs, Projects, Teams
- Active link is highlighted blue
- User initials shown at sidebar bottom

---

## Spec 7: Wiki Pages (End-to-End)

**Depends on:** Spec 5, Spec 6
**User stories:** US-WIKI-1 through US-WIKI-5

### What

First complete document type — wiki list, wiki view, create, edit, delete.

### Files
- `packages/web/src/pages/WikiList.tsx` — Table of all wikis
- `packages/web/src/pages/WikiView.tsx` — Single wiki (content + metadata sidebar)
- `packages/web/src/components/CreateDocumentModal.tsx` — Reusable create modal
- `packages/web/src/components/DeleteConfirmModal.tsx` — Reusable delete confirmation

### Verify
- Navigate to `/wiki` → see list of seeded wikis
- Click "+ New Wiki" → modal → fill title + body → submit → appears in list
- Click wiki row → navigates to `/wiki/:id` → shows content + metadata
- Click "Edit" → inline edit title + body → save → changes persist on reload
- Click "Delete" → confirmation → wiki disappears from list

---

## Spec 8: Programs (End-to-End)

**Depends on:** Spec 7 (reuses CreateDocumentModal, DeleteConfirmModal)
**User stories:** US-PROG-1 through US-PROG-8

### What

Programs list, program view with tabs (Overview, Issues, Projects, Weeks).

### Files
- `packages/api/src/routes/programs.ts` — GET /programs, GET /programs/:id (with project count), POST, PATCH, DELETE
- `packages/web/src/pages/ProgramsList.tsx` — Table of programs
- `packages/web/src/pages/ProgramView.tsx` — Tabbed view (Overview, Issues, Projects, Weeks)

### Verify
- `/programs` shows seeded programs with owner name and project count
- Create new program → appears in list
- Click program → Overview tab shows body + RACI fields
- Issues tab shows all issues from all projects in this program
- Projects tab shows projects belonging to this program
- Edit + Delete work

---

## Spec 9: Projects (End-to-End)

**Depends on:** Spec 8
**User stories:** US-PROJ-1 through US-PROJ-8

### What

Projects list, project view with tabs (Overview, Issues, Weeks, Retro placeholder).

### Files
- `packages/api/src/routes/projects.ts` — GET /projects, GET /projects/:id (with issue count + program), POST, PATCH, DELETE
- `packages/web/src/pages/ProjectsList.tsx` — Table of projects
- `packages/web/src/pages/ProjectView.tsx` — Tabbed view

### Verify
- `/projects` shows all projects with owner, issue count, ICE score, program name
- Create new project (with program association) → appears in list
- Click project → Overview tab shows body + ICE scores
- Issues tab shows all issues in this project
- Weeks tab shows issues grouped by week_number
- Retro tab shows placeholder "Coming soon"
- Edit ICE values → ICE score recalculates
- Delete works

---

## Spec 10: Issues (End-to-End)

**Depends on:** Spec 9
**User stories:** US-ISS-1 through US-ISS-8

### What

Issue creation, issue view with metadata sidebar, inline status/priority/assignee editing.

### Files
- `packages/api/src/routes/issues.ts` — GET /issues (with filters), GET /issues/:id, PATCH /issues/:id
- `packages/web/src/pages/IssueView.tsx` — Full issue view with metadata sidebar
- `packages/web/src/components/StatusBadge.tsx` — Colored status badge
- `packages/web/src/components/PriorityBadge.tsx` — Priority indicator

### Verify
- Create issue from project Issues tab (with project + program association)
- Click issue → `/issues/:id` → content + metadata sidebar
- Change status dropdown → saves immediately → badge color changes
- Change priority → saves
- Change assignee → saves
- Assign week number → issue appears in project Weeks tab
- Delete works

---

## Spec 11: Dashboard + Weeks

**Depends on:** Spec 10
**User stories:** US-DASH-1, US-DASH-2, US-WEEK-1, US-WEEK-2, US-WEEK-3

### What

Dashboard shows current user's sprint issues. Weeks tab on projects groups issues by week.

### Files
- `packages/web/src/pages/Dashboard.tsx` — "My Current Sprint" table
- `packages/api/src/routes/dashboard.ts` — GET /dashboard (issues assigned to current user in latest week)

### Verify
- Login as Alice → Dashboard shows only Alice's issues in the current week
- Click issue on dashboard → navigates to issue view
- Project Weeks tab correctly groups issues by week_number
- Assigning an issue to a week → it appears in the Weeks tab

---

## Spec 12: Teams Page

**Depends on:** Spec 6
**User stories:** US-TEAM-1

### What

Simple team member list.

### Files
- `packages/api/src/routes/users.ts` — GET /users
- `packages/web/src/pages/Teams.tsx` — Table of team members

### Verify
- `/teams` shows Alice and Bob with email and display name

---

## Spec 13: Seed Data

**Depends on:** Spec 3
**User stories:** None (data)

### What

Seed script that populates the database with realistic test data.

### File: packages/api/src/db/seed.ts

### Data to Seed
- 2 users (Alice, Bob) with bcrypt-hashed passwords
- 3 wiki documents
- 2 programs (Platform, Product)
- 3 projects (Auth Redesign, Dashboard v2, API Gateway) linked to programs
- 9 issues (3 per project) with varied statuses, priorities, assignees, weeks
- 12 week documents (4 per project)
- All document_associations linking projects→programs, issues→projects, issues→programs

### Verify
- `npx tsx packages/api/src/db/seed.ts` populates database
- `SELECT count(*) FROM documents` returns 29 (3 wiki + 2 programs + 3 projects + 9 issues + 12 weeks)
- `SELECT count(*) FROM users` returns 2

---

## Spec 14: End-to-End Verification

**Depends on:** All specs

### What

Full walkthrough verification of all flows.

### Checklist
- [ ] Login as Alice → Dashboard shows her sprint issues
- [ ] Navigate Wiki → see 3 wikis → create new → edit → delete
- [ ] Navigate Programs → see 2 programs → click Platform → Overview tab → Issues tab (shows issues from Auth Redesign + API Gateway) → Projects tab
- [ ] Navigate Projects → see 3 projects → click Auth Redesign → Overview → Issues → Weeks (grouped by week) → create new issue → assign to week → appears in Weeks tab
- [ ] Open issue → change status to "done" → change priority → reassign to Bob
- [ ] Login as Bob → Dashboard shows Bob's assigned issues
- [ ] All navigation flows work (sidebar, row clicks, tabs, back)
- [ ] Soft deletes work (deleted items don't appear in lists)
- [ ] Server stays running between all operations (persistent)

---

## Dependency Graph

```
Spec 1 (Scaffolding)
├── Spec 2 (Shared Types)
├── Spec 3 (Database)
│   ├── Spec 4 (Auth)
│   │   ├── Spec 5 (Documents CRUD)
│   │   │   ├── Spec 7 (Wiki E2E)
│   │   │   │   ├── Spec 8 (Programs E2E)
│   │   │   │   │   └── Spec 9 (Projects E2E)
│   │   │   │   │       └── Spec 10 (Issues E2E)
│   │   │   │   │           └── Spec 11 (Dashboard + Weeks)
│   │   │   └── (reused modals)
│   │   └── Spec 6 (Frontend Shell)
│   │       └── Spec 12 (Teams)
│   └── Spec 13 (Seed Data)
└── Spec 14 (Verification) — depends on ALL
```
