# HELM-BUILD1.md — First Build PRD

## What We're Building

**Helm** — a document-first project management tool for engineering teams. Everything is a document: programs, projects, issues, sprints, wiki pages. Different document types get different views, but they share a common data model underneath.

This is Build 1: the simplest vertical slice that proves the agent can scaffold a full-stack app, wire up a database, and connect frontend to backend. We add complexity in subsequent builds.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Express + TypeScript + Node.js |
| Database | SQLite (via better-sqlite3) |
| Frontend | React + Vite + TypeScript + TailwindCSS |
| Shared | TypeScript types shared between api and web |

## Project Structure

```
helm/
├── api/
│   ├── src/
│   │   ├── index.ts              # Express server entry
│   │   ├── database.ts           # SQLite setup, migrations
│   │   ├── routes/
│   │   │   └── documents.ts      # Document CRUD routes
│   │   └── middleware/
│   │       └── errors.ts         # Error handling middleware
│   ├── package.json
│   └── tsconfig.json
├── web/
│   ├── src/
│   │   ├── main.tsx              # React entry
│   │   ├── App.tsx               # Root component, routing
│   │   ├── api/
│   │   │   └── client.ts         # API client (fetch wrapper)
│   │   ├── pages/
│   │   │   ├── WorkspacePage.tsx  # Lists programs
│   │   │   ├── ProgramPage.tsx   # Lists projects in a program
│   │   │   └── ProjectPage.tsx   # Lists issues in a project
│   │   └── components/
│   │       ├── DocumentCard.tsx   # Reusable card for any document
│   │       ├── CreateDocumentForm.tsx
│   │       └── Layout.tsx        # Sidebar + main content layout
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── index.html
├── shared/
│   ├── types.ts                  # Shared TypeScript types
│   └── package.json
└── package.json                  # Root workspace config
```

## Data Model

The core insight: **one table, many types.** Every entity is a document.

```typescript
// shared/types.ts

type DocumentType = 'workspace' | 'program' | 'project' | 'issue';

interface Document {
  id: string;                    // UUID
  type: DocumentType;
  title: string;
  content: string;               // Markdown body
  parentId: string | null;       // Parent document (hierarchy)
  status: string;                // Type-specific: 'active', 'backlog', 'in_progress', 'done', etc.
  priority: string | null;       // 'low' | 'medium' | 'high' | 'critical' (for issues)
  createdAt: string;             // ISO timestamp
  updatedAt: string;             // ISO timestamp
}

// The hierarchy:
// workspace (parentId: null)
//   └── program (parentId: workspace.id)
//        └── project (parentId: program.id)
//             └── issue (parentId: project.id)
```

**Why one table?** Because "everything is a document" means a program and an issue share the same fundamental shape: a title, content (markdown), a parent, metadata. The `type` field determines how the UI renders it. Adding new document types later (sprints, wiki pages) is just adding a new `type` value — no schema migration, no new tables, no new CRUD routes.

## Build 1 Scope

### What's IN Build 1

**Backend (API):**
1. Express server with JSON middleware and error handling
2. SQLite database with a single `documents` table
3. Database migration that creates the table on startup
4. CRUD routes for documents:
   - `POST /api/documents` — create a document (type, title, content, parentId)
   - `GET /api/documents?type=X&parentId=Y` — list documents filtered by type and/or parent
   - `GET /api/documents/:id` — get a single document
   - `PUT /api/documents/:id` — update a document
   - `DELETE /api/documents/:id` — delete a document
5. Seed data: one workspace, two programs, two projects (one per program), three issues per project

**Frontend (Web):**
1. React app with Vite + TailwindCSS
2. React Router for navigation
3. API client (thin fetch wrapper)
4. Three pages:
   - **Workspace page** (`/`): Shows the workspace name, lists programs as cards
   - **Program page** (`/programs/:id`): Shows program name, lists its projects as cards
   - **Project page** (`/projects/:id`): Shows project name, lists its issues as a simple list with status badges
5. Reusable `DocumentCard` component (renders any document type as a clickable card)
6. `CreateDocumentForm` component (title + content + type, used on all pages)
7. Basic `Layout` component (sidebar with workspace name + navigation, main content area)

**Shared:**
1. TypeScript types for Document, DocumentType, CreateDocumentInput, UpdateDocumentInput

### What's NOT in Build 1

- No authentication (no users, no login)
- No sprints
- No wiki/documents section
- No kanban board view
- No drag-and-drop
- No real-time updates
- No search
- No labels/tags
- No comments
- No assignments
- No file attachments
- No rich text editor (just plain text/markdown for now)

## Instructions for the Agent

Feed these to Shipyard one at a time. Each instruction is a logical unit of work. Document what happens after each one.

### Instruction 1: Project Scaffolding
```
Create a new project called "helm" with a monorepo structure. Set up three packages: api (Express + TypeScript), web (React + Vite + TypeScript + TailwindCSS), and shared (TypeScript types). Configure the root package.json with workspaces. Make sure each package has its own tsconfig.json. The api should run on port 3001 and the web dev server on port 5173. Add a proxy config in vite so the web app can call /api/* and have it forwarded to the api server.
```

**What this tests:** Can the agent scaffold a multi-package project from scratch? Does it handle package.json workspaces? Does it configure Vite proxy correctly? This is pure `create_file` work — no editing.

**Expected difficulty:** Easy. But watch for: incorrect workspace config, missing tsconfig paths, wrong Vite proxy setup.

### Instruction 2: Shared Types
```
Create the shared types in shared/types.ts. Define a DocumentType union type with values 'workspace', 'program', 'project', 'issue'. Define a Document interface with fields: id (string), type (DocumentType), title (string), content (string), parentId (string | null), status (string), priority (string | null), createdAt (string), updatedAt (string). Also define CreateDocumentInput (type, title, content, parentId, status, priority) and UpdateDocumentInput (partial of title, content, status, priority). Export everything.
```

**What this tests:** Can the agent create clean TypeScript types? Simple `create_file` task.

**Expected difficulty:** Easy.

### Instruction 3: Database Setup
```
Set up SQLite in the api package. Install better-sqlite3 and its type definitions. Create api/src/database.ts that initializes a SQLite database at ./helm.db, creates a documents table matching the shared Document type if it doesn't exist, and exports the database instance. The table should have: id (TEXT PRIMARY KEY), type (TEXT NOT NULL), title (TEXT NOT NULL), content (TEXT DEFAULT ''), parent_id (TEXT), status (TEXT DEFAULT 'active'), priority (TEXT), created_at (TEXT), updated_at (TEXT). Add a seed function that inserts: one workspace called "Engineering", two programs ("Platform" and "Product") under the workspace, one project under each program, and two issues under each project with different statuses.
```

**What this tests:** Can the agent install dependencies (`run_command` for npm install), create database setup code, handle SQL schema definition? First use of `run_command`.

**Expected difficulty:** Easy-medium. Watch for: forgetting to install @types/better-sqlite3, wrong column types, seed data not referencing correct parent IDs.

### Instruction 4: API Routes
```
Create the document CRUD routes in api/src/routes/documents.ts. Implement:
- POST /api/documents: Create a document. Generate a UUID for the id. Set createdAt and updatedAt to current ISO timestamp. Return the created document.
- GET /api/documents: List documents. Support query params: type (filter by document type), parentId (filter by parent). Return array of documents.
- GET /api/documents/:id: Get a single document by id. Return 404 if not found.
- PUT /api/documents/:id: Update a document. Only update fields that are provided. Update the updatedAt timestamp. Return 404 if not found.
- DELETE /api/documents/:id: Delete a document. Return 404 if not found.

Create error handling middleware in api/src/middleware/errors.ts. Wire up the routes and middleware in api/src/index.ts. Make sure the server calls the database init and seed function on startup.
```

**What this tests:** Multiple file creation + editing the existing index.ts to wire things up. The agent needs to understand Express routing patterns and reference the shared types.

**Expected difficulty:** Medium. Watch for: forgetting to import routes in index.ts, wrong HTTP status codes, not handling the case where seed data already exists (double-seeding on restart).

### Instruction 5: API Client
```
Create a simple API client in web/src/api/client.ts. It should be a thin wrapper around fetch with:
- A base URL pointing to /api
- Methods: getDocuments(params?: {type?: string, parentId?: string}), getDocument(id: string), createDocument(input: CreateDocumentInput), updateDocument(id: string, input: UpdateDocumentInput), deleteDocument(id: string)
- All methods should return typed responses using the shared Document type
- Handle errors by throwing with the response status and message
```

**What this tests:** Can the agent create a frontend module that imports shared types? Does it understand the API contract it just built?

**Expected difficulty:** Easy-medium. Watch for: import path issues between packages, incorrect URL construction for query params.

### Instruction 6: Layout and Document Components
```
Create the Layout component in web/src/components/Layout.tsx. It should have a sidebar (fixed width, dark background) with the workspace name at the top and navigation links, and a main content area. Use TailwindCSS for styling.

Create the DocumentCard component in web/src/components/DocumentCard.tsx. It takes a Document and renders a card showing the title, type badge, status badge, and a truncated preview of the content. The card should be clickable. Style the type badge with different colors per document type: program=blue, project=green, issue=purple.

Create the CreateDocumentForm component in web/src/components/CreateDocumentForm.tsx. Simple form with title input, content textarea, and a submit button. It receives the document type and parentId as props (so the page determines what type of document is being created). On submit, call the API client's createDocument method.
```

**What this tests:** Multiple component creation, TailwindCSS usage, component composition patterns. First real frontend work.

**Expected difficulty:** Medium. Watch for: TailwindCSS classes that don't exist (agent might hallucinate class names), missing imports, incorrect prop types.

### Instruction 7: Pages and Routing
```
Set up React Router in web/src/App.tsx with routes:
- / → WorkspacePage
- /programs/:id → ProgramPage
- /projects/:id → ProjectPage

Create WorkspacePage.tsx: On mount, fetch the workspace document (type=workspace), then fetch its children (type=program, parentId=workspace.id). Show the workspace title and a grid of DocumentCards for the programs. Include a CreateDocumentForm for adding new programs.

Create ProgramPage.tsx: Fetch the program document by id from the URL params, then fetch its children (type=project). Show the program title, breadcrumb (Workspace > Program), grid of project DocumentCards, and a CreateDocumentForm for new projects.

Create ProjectPage.tsx: Fetch the project by id, then fetch its children (type=issue). Show the project title, breadcrumb (Workspace > Program > Project), list of issues with status badges (different from card grid — use a table or list layout), and a CreateDocumentForm for new issues. Issues should show title, status, and priority.
```

**What this tests:** This is the most complex instruction. Multiple files, React Router setup, data fetching, component composition, conditional rendering. The agent needs to maintain consistency across all pages.

**Expected difficulty:** Medium-hard. Watch for: React Router v6 vs v5 syntax confusion, useEffect data fetching patterns, breadcrumb requiring parent document lookups, key prop warnings.

### Instruction 8: Polish and Verify
```
Start both the api and web servers. Fix any TypeScript compilation errors. Fix any runtime errors. Make sure you can:
1. See the workspace page with the two seeded programs
2. Click into a program and see its projects
3. Click into a project and see its issues
4. Create a new issue from the project page
5. The new issue appears in the list without a page refresh
```

**What this tests:** Can the agent debug its own work? Does it use `run_command` to start servers, check for errors, and iterate? This instruction requires the agent to run the project and fix what's broken.

**Expected difficulty:** Medium-hard. This is where most issues from previous instructions surface. The agent needs to read error output, trace it to the right file, and make surgical fixes.

## After Build 1

Record for each instruction:
- Pass/fail
- Number of interventions
- What went wrong (if anything)
- How the agent recovered (or didn't)
- Total tool calls and tokens

This data determines what to fix in Shipyard before Build 2.

### Build 2 Preview (not yet — do after Build 1 feedback)
- Add issue detail page with markdown rendering
- Add sprint documents (type: 'sprint', parentId: project)
- Add sprint view (which issues are in this sprint)
- Add status workflow (backlog → in_progress → review → done)
- Add assignee field to issues

### Build 3 Preview
- Wiki/documents section (type: 'wiki', parentId: workspace)
- Kanban board view for projects (drag issues between status columns)
- Authentication (users, login, workspace membership)
- Search across all documents
