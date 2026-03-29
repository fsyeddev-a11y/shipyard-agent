# HELM-BUILD1.md — First Build PRD

## What We're Building

**Helm** — a document-first project management tool for engineering teams. Everything is a document: programs, projects, issues, sprints, wiki pages. Different document types get different views, but they share a common data model underneath.

This is Build 1: the simplest vertical slice — scaffold a full-stack app, wire up a database, and connect frontend to backend.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Express + TypeScript + Node.js |
| Database | SQLite via **sql.js** (pure JS, no native compilation) |
| Frontend | React 18 + Vite 4 + TypeScript + TailwindCSS |
| Shared | TypeScript types shared between api and web |
| Runtime | Use `npx tsx` to run TypeScript files. Install `tsx` as a dev dependency. |

## Dependency Versions (pin these exactly)

Install these specific versions. Do NOT use `@latest` — the system runs Node 20.16.

```
# Backend
express@4           @types/express@4      @types/node@20
sql.js@1            uuid@9                @types/uuid@9
tsx@4               typescript@5

# Frontend
react@18            react-dom@18          react-router-dom@6
@types/react@18     @types/react-dom@18
vite@4.5            @vitejs/plugin-react@4.2
tailwindcss@3

# All installs from project root using workspace flag:
# npm install <pkg> -w packages/api
# npm install <pkg> -w packages/web
```

## Data Model

One table, many types. Every entity is a document.

```typescript
type DocumentType = 'workspace' | 'program' | 'project' | 'issue';

interface Document {
  id: string;                    // UUID
  type: DocumentType;
  title: string;
  content: string;               // Markdown body
  parentId: string | null;       // Parent document (hierarchy)
  status: string;                // 'active', 'open', 'closed', 'in_progress', 'done'
  priority: string | null;       // 'low' | 'medium' | 'high' | 'critical' (issues only)
  createdAt: string;             // ISO timestamp
  updatedAt: string;             // ISO timestamp
}

// Hierarchy:
// workspace (parentId: null)
//   └── program (parentId: workspace.id)
//        └── project (parentId: program.id)
//             └── issue (parentId: project.id)
```

SQL table uses snake_case columns: `parent_id`, `created_at`, `updated_at`. The API must map these to camelCase (parentId, createdAt, updatedAt) in all responses.

**sql.js note:** `db.exec()` returns `{columns: [...], values: [[...]]}` — raw arrays, NOT objects. Always map query results to typed Document objects with camelCase field names.

## Build 1 Scope

### What's IN

**Backend:**
- Express server with `express.json()` middleware and error handling
- SQLite database (sql.js) with a single `documents` table
- Table created on startup if it doesn't exist
- CRUD routes:
  - `POST /api/documents` — create (generate UUID, set timestamps)
  - `GET /api/documents?type=X&parentId=Y` — list with optional filters
  - `GET /api/documents/:id` — get one (404 if not found)
  - `PUT /api/documents/:id` — update provided fields only (404 if not found)
  - `DELETE /api/documents/:id` — delete (404 if not found)
- Seed data: 1 workspace "Engineering", 2 programs, 2 projects, 4 issues with different statuses
- Seed function must check if data exists before inserting (no duplicates on restart)

**Frontend:**
- React app with Vite + TailwindCSS
- React Router v6 for navigation
- API client (thin fetch wrapper, string concatenation for URLs — not URL constructor)
- Three pages:
  - **Workspace page** (`/`): workspace title, grid of program cards, create program form
  - **Program page** (`/programs/:id`): program title, breadcrumb, grid of project cards, create project form
  - **Project page** (`/projects/:id`): project title, breadcrumb, list of issues with status/priority badges, create issue form
- Reusable components: DocumentCard, CreateDocumentForm, Layout (sidebar + main)

**Shared:**
- TypeScript types: Document, DocumentType, CreateDocumentInput, UpdateDocumentInput

### What's NOT in Build 1

No authentication, no sprints, no wiki, no kanban, no drag-and-drop, no real-time, no search, no labels, no comments, no assignments, no file attachments, no rich text editor.

## UI Wireframes

### Workspace Page (`/`)

```
┌─────────────────┬──────────────────────────────────────────┐
│                 │                                          │
│  HELM           │  Engineering                             │
│                 │                                          │
│  • Workspace    │  ┌─────────────┐  ┌─────────────┐       │
│                 │  │ Platform    │  │ Product     │       │
│                 │  │ program     │  │ program     │       │
│                 │  │ active      │  │ active      │       │
│                 │  └─────────────┘  └─────────────┘       │
│                 │                                          │
│                 │  ┌──────────────────────────────┐       │
│                 │  │ Title: [_______________]     │       │
│                 │  │ Content: [______________]    │       │
│                 │  │ [Create Program]             │       │
│                 │  └──────────────────────────────┘       │
│                 │                                          │
└─────────────────┴──────────────────────────────────────────┘
```

- Sidebar: w-64, bg-gray-900, text-white, min-h-screen
- Cards: border, rounded-lg, p-4, hover:shadow-md, cursor-pointer
- Type badge: small rounded pill (bg-blue-500 for program, bg-green-500 for project, bg-purple-500 for issue), text-white, text-xs, px-2, py-1

### Program Page (`/programs/:id`)

```
┌─────────────────┬──────────────────────────────────────────┐
│                 │                                          │
│  HELM           │  Workspace > Platform                    │
│                 │                                          │
│  • Workspace    │  Platform                                │
│                 │                                          │
│                 │  ┌─────────────┐                         │
│                 │  │ Project A   │                         │
│                 │  │ project     │                         │
│                 │  │ active      │                         │
│                 │  └─────────────┘                         │
│                 │                                          │
│                 │  [Title] [Content] [Create Project]      │
│                 │                                          │
└─────────────────┴──────────────────────────────────────────┘
```

- Breadcrumb: "Workspace" is a link to `/`, program name is plain text
- Cards link to `/projects/:id`

### Project Page (`/projects/:id`)

```
┌─────────────────┬──────────────────────────────────────────┐
│                 │                                          │
│  HELM           │  Workspace > Platform > Project A        │
│                 │                                          │
│  • Workspace    │  Project A                               │
│                 │                                          │
│                 │  Issues:                                  │
│                 │  ┌────────────────────────────────────┐  │
│                 │  │ Issue 1    [open]     priority: -  │  │
│                 │  │ Issue 2    [closed]   priority: -  │  │
│                 │  └────────────────────────────────────┘  │
│                 │                                          │
│                 │  [Title] [Content] [Create Issue]         │
│                 │                                          │
└─────────────────┴──────────────────────────────────────────┘
```

- Breadcrumb: "Workspace" links to `/`, "Platform" links to `/programs/:id`, project name is plain text
- Issues are a list, not cards — show title, status badge (color-coded), priority
- Status badge colors: open=bg-blue-400, closed=bg-red-400, in_progress=bg-yellow-400, done=bg-green-400, active=bg-gray-400

## Instructions for the Agent

You are building the Helm app. Read this entire PRD, then plan and implement it.

**How to work:**
1. Read this PRD fully before writing any code.
2. Plan the work — break it into specs, decide on directory structure and file paths. Write your plan to `.shipyard/notes/plan.md`.
3. Implement one spec at a time. After each spec, verify it works. Write progress to `.shipyard/notes/progress.md`.
4. If you get stuck on something, write what's blocking you to `.shipyard/notes/issues.md` and move on to the next spec.
5. At the end, verify the full app works end-to-end.

**High-level build order (you decide the exact specs and file paths):**

1. **Monorepo scaffolding** — set up the project structure with separate backend, frontend, and shared type packages. Configure TypeScript, workspaces, and the Vite dev server proxy. Install all dependencies.

2. **Shared types** — define the Document data model and input types.

3. **Database** — set up sql.js, create the documents table, write the seed function with idempotency check.

4. **API routes** — implement CRUD endpoints. Wire them into the Express server entry point. Verify each route works with curl.

5. **API client** — create the frontend fetch wrapper that calls the API routes.

6. **Reusable components** — Layout (sidebar + main), DocumentCard (clickable card with type/status badges), CreateDocumentForm (title + content + submit).

7. **Pages and routing** — WorkspacePage, ProgramPage, ProjectPage with React Router v6. Each page fetches data, renders components, and supports creating new documents.

8. **Verification** — start both servers, test the full flow: workspace → programs → projects → issues → create new issue.

**Verification criteria (the app is done when):**
- [ ] API server starts without errors on port 3001
- [ ] `GET /api/documents?type=workspace` returns the Engineering workspace as a JSON object (not array of arrays)
- [ ] `GET /api/documents?type=program&parentId=<workspace-id>` returns Platform and Product
- [ ] `POST /api/documents` creates a new document and returns it with id and timestamps
- [ ] Web dev server starts on port 5173
- [ ] Browser shows workspace page with "Engineering" title and two program cards
- [ ] Clicking a program navigates to program page with breadcrumb and project cards
- [ ] Clicking a project navigates to project page with breadcrumb and issue list
- [ ] Creating a new issue from the project page adds it to the list without page refresh
- [ ] Sidebar with "Helm" branding and Workspace link is visible on all pages

## After Build 1

Record:
- Pass/fail per spec
- Number of interventions
- What went wrong
- Total tool calls and tokens

### Build 2 Preview
- Issue detail page with markdown rendering
- Sprint documents (type: 'sprint')
- Status workflow (backlog → in_progress → review → done)
- Assignee field

### Build 3 Preview
- Wiki/documents section
- Kanban board view
- Authentication
- Search
