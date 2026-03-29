# HELM-BUILD1.md — First Build PRD

## What We're Building

**Helm** — a document-first project management tool for engineering teams. Everything is a document: programs, projects, issues, sprints, wiki pages. Different document types get different views, but they share a common data model underneath.

This is Build 1: the simplest vertical slice — scaffold a full-stack app, wire up a database, and connect frontend to backend.

## Tech Stack & Versions

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Express + TypeScript | express@4, typescript@5 |
| Database | SQLite via sql.js | sql.js@1 |
| Frontend | React + Vite + TailwindCSS | react@18, react-dom@18, vite@4.5, tailwindcss@3 |
| Routing | React Router | react-router-dom@6 |
| Shared | TypeScript types | shared between api and web |
| Runtime | tsx (run TypeScript directly) | tsx@4 |
| IDs | UUID generation | uuid@9 |

**Node version:** 20.16. Do NOT install packages that require Node 20.19+.

**Install from project root using workspace flags:**
```bash
npm install express uuid sql.js -w packages/api
npm install -D tsx typescript @types/express @types/node @types/uuid -w packages/api
npm install react@18 react-dom@18 react-router-dom@6 -w packages/web
npm install -D @types/react@18 @types/react-dom@18 vite@4.5 @vitejs/plugin-react@4.2 tailwindcss@3 -w packages/web
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

**SQL table** — uses snake_case columns. The API MUST map to camelCase in all responses.

```sql
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT DEFAULT '',
  parent_id TEXT,
  status TEXT DEFAULT 'active',
  priority TEXT,
  created_at TEXT,
  updated_at TEXT
);
```

**Seed data** — insert ALL of these on first startup (check if table is empty first):

| id | type | title | parent_id | status |
|----|------|-------|-----------|--------|
| 1 | workspace | Engineering | null | active |
| 2 | program | Platform | 1 | active |
| 3 | program | Product | 1 | active |
| 4 | project | Project A | 2 | active |
| 5 | project | Project B | 3 | active |
| 6 | issue | Issue 1 | 4 | open |
| 7 | issue | Issue 2 | 4 | closed |
| 8 | issue | Issue 3 | 5 | open |
| 9 | issue | Issue 4 | 5 | closed |

## Implementation Patterns (use these exactly)

### Backend: Express server (packages/api/src/index.ts)

```typescript
import express from 'express';
import { initDb, db } from './db';
import documentRoutes from './routes/documents';

const app = express();
const PORT = 3001;  // MUST be 3001

app.use(express.json());  // MUST use express.json(), NOT body-parser
app.use('/api/documents', documentRoutes);

// Error handling middleware — MUST be last
app.use((err: any, req: any, res: any, next: any) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

// Initialize DB and seed, THEN start server
initDb().then(() => {
  app.listen(PORT, () => {
    console.log(`API server running on http://localhost:${PORT}`);
  });
});
```

### Backend: sql.js database (packages/api/src/db.ts)

```typescript
import initSqlJs, { Database } from 'sql.js';

let db: Database;

async function initDb() {
  const SQL = await initSqlJs();
  db = new SQL.Database();
  // Create table...
  // Seed data if empty...
}

// db.exec() returns [{ columns: [...], values: [[...], ...] }]
// ALWAYS null-check: result[0]?.values || []
// ALWAYS map to camelCase objects:
function mapRow(row: any[]) {
  return {
    id: row[0], type: row[1], title: row[2], content: row[3],
    parentId: row[4], status: row[5], priority: row[6],
    createdAt: row[7], updatedAt: row[8],
  };
}

export { initDb, db, mapRow };
```

### Frontend: React entry (packages/web/src/main.tsx)

```tsx
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(<App />);
```

Do NOT use `ReactDOM.render` — that's React 17. Do NOT import from `react-dom` — use `react-dom/client`.

### Frontend: React Router (packages/web/src/App.tsx)

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
// Use Routes + Route with element prop. Do NOT use Switch (that's v5).
// BrowserRouter goes here ONLY — not in main.tsx too.
```

### Frontend: API client (packages/web/src/apiClient.ts)

```typescript
const BASE_URL = '/api';  // Relative URL — goes through Vite proxy. Do NOT use http://localhost:3001
// Use fetch(), NOT axios
```

### Frontend: Vite config (packages/web/vite.config.ts)

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
});
```

### Frontend: Required files

These files MUST exist for Vite to work:

1. **packages/web/index.html** — with `<div id="root"></div>` and `<script type="module" src="/src/main.tsx"></script>`
2. **packages/web/src/main.tsx** — React entry with createRoot
3. **packages/web/src/index.css** — with `@tailwind base; @tailwind components; @tailwind utilities;`
4. **packages/web/tailwind.config.js** — with content: `['./src/**/*.{ts,tsx}']`

## Build 1 Scope

### What's IN

**Backend:**
- Express server on port 3001 with `express.json()` middleware
- sql.js database with documents table (schema above)
- All 9 seed records inserted on startup
- CRUD routes: POST, GET (with type/parentId filters), GET by id, PUT, DELETE
- Error handling middleware

**Frontend:**
- React 18 app with Vite 4 + TailwindCSS 3
- React Router v6 for navigation
- API client using fetch with relative `/api` URLs
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
3. Implement one spec at a time. After each spec, verify it works. Append progress to `.shipyard/notes/progress.md`.
4. If you get stuck on something, write what's blocking you to `.shipyard/notes/issues.md` and move on to the next spec.
5. At the end, verify the full app works end-to-end.

**High-level build order (you decide the exact specs and file paths):**

1. **Monorepo scaffolding** — set up the project structure with packages/api, packages/web, packages/shared. Configure TypeScript, workspaces, and the Vite dev server proxy. Install ALL dependencies using the exact versions and commands listed above.

2. **Shared types** — define the Document data model and input types.

3. **Database** — set up sql.js using the pattern above. Create the documents table with the exact schema above. Seed ALL 9 records from the seed data table. The `initDb` function must be async and called before the server starts.

4. **API routes** — implement CRUD endpoints. Use the `mapRow` helper to convert sql.js arrays to camelCase objects. Wire routes into Express at `/api/documents`. Server MUST listen on port 3001.

5. **API client** — create fetch wrapper using relative `/api` URLs (NOT http://localhost:3001). Do NOT use axios.

6. **Reusable components** — Layout (sidebar + main), DocumentCard (clickable card with type/status badges), CreateDocumentForm (title + content + submit).

7. **Pages and routing** — WorkspacePage, ProgramPage, ProjectPage with React Router v6 using Routes/Route/element pattern. Each page fetches data, renders components, and supports creating new documents.

8. **Verification** — test the full flow: workspace → programs → projects → issues → create new issue.

**Verification criteria (the app is done when):**
- [ ] API server starts without errors on port 3001
- [ ] `GET /api/documents?type=workspace` returns the Engineering workspace as a JSON object
- [ ] `GET /api/documents?type=program&parentId=1` returns Platform and Product
- [ ] `POST /api/documents` creates a new document and returns it with id and timestamps
- [ ] Web dev server starts on port 5173
- [ ] Browser shows workspace page with "Engineering" title and two program cards
- [ ] Clicking a program navigates to program page with breadcrumb and project cards
- [ ] Clicking a project navigates to project page with breadcrumb and issue list
- [ ] Creating a new issue from the project page adds it to the list
- [ ] Sidebar with "Helm" branding and Workspace link is visible on all pages
