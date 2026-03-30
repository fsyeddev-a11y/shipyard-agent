# SHIP-PRD.md — Ship App Rebuild PRD

## Overview

Ship is a project management tool where **everything is a document**. Wikis, Programs, Projects, Issues, and Weeks are all stored as rows in a single `documents` table differentiated by `document_type`. Users log in, see their dashboard, and navigate a sidebar to manage work across organizational programs and projects.

This PRD defines the **complete rebuild** to be executed by the Shipyard coding agent. The agent should read this document, break it into specs, and implement each spec vertically (create + verify + fix before moving on).

---

## Tech Stack (Pinned Versions)

| Layer | Technology | Version | Why |
|-------|-----------|---------|-----|
| **Backend** | Express (TypeScript) | 4.21.2 | Mature, async, rich middleware ecosystem |
| **Database** | PostgreSQL via `pg` | 8.13.1 | JSONB for type-specific properties, proven at scale |
| **Frontend** | React | 18.3.1 | Component model, hooks, lazy loading |
| **Build** | Vite | 6.0.5 | Fast HMR, native ESM |
| **Routing** | React Router | 7.1.1 | Lazy-loaded pages, nested routes |
| **State** | TanStack React Query | 5.62.0 | Server-state caching, auto-refetch |
| **Styling** | Tailwind CSS | 3.4.17 | Utility-first, dark mode support |
| **Rich Text Editor** | TipTap | 2.11.5 | Extensible, clean JSON output |
| **Validation** | Zod | 3.24.1 | Runtime validation, TypeScript inference |
| **Auth** | bcryptjs + express-session | 3.0.3 / 1.18.1 | Password hashing + secure session cookies |
| **UUID** | uuid | 11.0.3 | Document IDs |
| **TypeScript** | typescript | 5.7.2 | Strict mode, shared types |
| **Dev runner** | tsx | 4.19.2 | Fast TypeScript execution |
| **Package manager** | npm workspaces | — | Monorepo structure |

### Monorepo Structure

```
ship/
├── packages/
│   ├── api/          # Express backend
│   ├── web/          # React frontend
│   └── shared/       # Shared TypeScript types
├── package.json      # Root workspace config
└── tsconfig.json     # Root TypeScript config
```

### Key Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `@types/express` | ^5.0.0 | Express type definitions |
| `@types/pg` | ^8.11.0 | PostgreSQL type definitions |
| `@types/bcryptjs` | ^2.4.0 | bcrypt type definitions |
| `@types/uuid` | ^10.0.0 | UUID type definitions |
| `@types/express-session` | ^1.18.0 | Session type definitions |
| `autoprefixer` | ^10.4.20 | Tailwind PostCSS |
| `postcss` | ^8.4.49 | CSS processing |

---

## Authentication

### Login Flow
1. User navigates to `/login`
2. Enters email + password
3. POST `/api/auth/login` — server validates bcrypt hash
4. Server creates session row in `sessions` table, sets httpOnly secure cookie
5. All subsequent requests include session cookie automatically
6. Middleware validates session on every protected route

### Session Schema
```sql
CREATE TABLE sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  expires_at TIMESTAMPTZ NOT NULL,
  last_activity TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Rules
- Session expires after 12 hours absolute
- Session refreshes `last_activity` on each request
- 15-minute inactivity timeout
- Logout deletes session row and clears cookie
- All routes except `/api/auth/login` and `/api/health` require valid session

---

## Data Model

### Core Principle: Everything is a Document

All entity types (wiki, issue, project, program, week) live in a single `documents` table. Type-specific fields live in a `properties` JSONB column. Relationships between documents are stored in `document_associations`.

### Tables

See [DATA-MODELS.md](./DATA-MODELS.md) for complete SQL schemas, all column definitions, indexes, and seed data.

### Document Types

| Type | Description | Key Properties |
|------|-------------|---------------|
| `wiki` | Organizational knowledge docs | `maintainer_id` |
| `program` | Highest-level container | `owner_id`, `approver_id`, `consulted_id`, `informed_id` |
| `project` | Feature-level container inside a program | `owner_id`, `approver_id`, `impact`, `confidence`, `ease`, `ice_score`, `design_approved` |
| `issue` | Task/story assigned to users | `status`, `priority`, `assignee_id`, `time_estimate`, `week_number` |
| `week` | Sprint container (read-only, computed) | `week_number` |

---

## API Endpoints

### Authentication
```
POST   /api/auth/login        { email, password } → { user, session }
POST   /api/auth/logout        → 200
GET    /api/auth/me            → { user } (current session)
```

### Documents (Unified CRUD)
```
GET    /api/documents          ?type=wiki|issue|project|program|week → Document[]
GET    /api/documents/:id      → Document (full, with associations)
POST   /api/documents          { document_type, title, ... } → Document
PATCH  /api/documents/:id      { title?, body?, properties? } → Document
DELETE /api/documents/:id      → 204 (soft delete)
```

### Issues (Type-Specific)
```
GET    /api/issues                  ?project_id=&program_id=&status=&assignee_id= → Issue[]
GET    /api/issues/:id              → Issue (with project + program associations)
PATCH  /api/issues/:id              { status?, priority?, assignee_id?, week_number? }
```

### Programs
```
GET    /api/programs                → Program[]
GET    /api/programs/:id            → Program (with projects + issue counts)
POST   /api/programs                { title, body?, properties? }
PATCH  /api/programs/:id            { title?, body?, properties? }
DELETE /api/programs/:id            → 204
```

### Projects
```
GET    /api/projects                ?program_id= → Project[]
GET    /api/projects/:id            → Project (with issues + week data)
POST   /api/projects                { title, body?, program_id, properties? }
PATCH  /api/projects/:id            { title?, body?, properties? }
DELETE /api/projects/:id            → 204
```

### Weeks
```
GET    /api/weeks                   ?project_id= → Week[] (computed from issues)
GET    /api/weeks/:id               → Week (with assigned issues)
```

### Users
```
GET    /api/users                   → User[] (team members)
GET    /api/users/:id               → User
```

---

## Pages & Navigation

### Sidebar (persistent, all pages)
```
Dashboard
Wiki
Programs
Projects
Teams
---
Settings (bottom)
Profile/Account (bottom)
```

### Page Inventory

| Page | Route | Description |
|------|-------|-------------|
| Login | `/login` | Email + password form |
| Dashboard | `/` | Current sprint issues for logged-in user |
| Wiki List | `/wiki` | All wiki documents in a list |
| Wiki View | `/wiki/:id` | Single wiki document (title, body, metadata sidebar) |
| Programs List | `/programs` | All programs in a table |
| Program View | `/programs/:id` | Program detail with tabs: Overview, Issues, Projects, Weeks |
| Projects List | `/projects` | All projects in a table |
| Project View | `/projects/:id` | Project detail with tabs: Overview, Issues, Weeks, Retro |
| Issue View | `/issues/:id` | Issue document with metadata sidebar |
| Teams | `/teams` | Team member list |

### Navigation Flows

1. **Wiki flow:** Sidebar "Wiki" → Wiki List → click row → Wiki View (by ID)
2. **Program flow:** Sidebar "Programs" → Programs List → click row → Program View → tabs switch between Overview/Issues/Projects/Weeks
3. **Program → Issues:** Program View "Issues" tab → lists all issues across all projects in the program → click issue → Issue View
4. **Program → Projects:** Program View "Projects" tab → lists projects in program → click project → Project View
5. **Project flow:** Sidebar "Projects" → Projects List → click row → Project View → tabs switch between Overview/Issues/Weeks/Retro
6. **Project → Issues:** Project View "Issues" tab → lists issues in the project → click issue → Issue View
7. **Project → Weeks:** Project View "Weeks" tab → shows sprint plan for current week with assigned issues

---

## Wireframes

See [WIREFRAMES.md](./WIREFRAMES.md) for ASCII wireframes of every page and view.

---

## Implementation Order (Vertical Slices)

See [SPECS.md](./SPECS.md) for the ordered spec list with dependencies. Each spec is independently verifiable.

**Critical path:**
1. Monorepo scaffolding + database setup
2. Auth (users table + sessions + login)
3. Documents CRUD (unified table + API)
4. Wiki pages (first document type, end-to-end)
5. Programs (second doc type + associations)
6. Projects (third doc type + program association)
7. Issues (fourth doc type + status/priority/assignment)
8. Weeks view (computed from issues, read-only)
9. Dashboard (current user's sprint issues)
10. Polish + verification

---

## Seed Data

The database should be seeded with realistic data so the app is immediately usable:

- **2 users:** alice@ship.dev (password: `password123`), bob@ship.dev (password: `password123`)
- **3 wiki docs:** "Engineering Handbook", "Onboarding Guide", "API Standards"
- **2 programs:** "Platform", "Product"
- **3 projects:** "Auth Redesign" (Platform), "Dashboard v2" (Product), "API Gateway" (Platform)
- **9 issues:** 3 per project, varied statuses/priorities/assignees/weeks
- **4 weeks:** Week 1-4 for each project

---

## Constraints for the Coding Agent

1. **No placeholder code.** Every file must have real, functional implementations.
2. **Vertical development.** Create → verify → fix before moving to next file.
3. **Install dependencies first.** Before importing any package, install it.
4. **Use pinned versions.** Install exact versions listed in the Tech Stack table.
5. **PostgreSQL required.** Use `pg` client directly (no ORM). Connection string from `DATABASE_URL` env var.
6. **Tailwind for all styling.** No inline styles, no CSS modules.
7. **React Router v7 patterns.** Use `BrowserRouter`, `Routes`, `Route`. Lazy-load pages.
8. **Express middleware order matters.** json() → cookieParser → session → authMiddleware → routes.
9. **All IDs are UUIDs.** Generated server-side via `uuid` package.
10. **Soft delete only.** Set `deleted_at` timestamp, never hard delete.
