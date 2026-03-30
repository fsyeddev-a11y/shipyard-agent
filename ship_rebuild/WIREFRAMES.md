# WIREFRAMES.md — Ship App Page Wireframes

Every page below is what the coding agent must implement. The sidebar is persistent across all authenticated pages.

---

## Shared Layout

```
+------------------+----------------------------------------------+
|                  |                                              |
|   SIDEBAR        |              MAIN CONTENT                   |
|   (fixed left)   |              (scrollable)                   |
|                  |                                              |
|   Dashboard      |                                              |
|   Wiki           |                                              |
|   Programs       |                                              |
|   Projects       |                                              |
|   Teams          |                                              |
|                  |                                              |
|                  |                                              |
|                  |                                              |
|                  |                                              |
|                  |                                              |
|   ----------     |                                              |
|   Settings       |                                              |
|   [Avatar] FS    |                                              |
+------------------+----------------------------------------------+
```

- Sidebar: 240px fixed width, dark bg (gray-900), white text
- Active link highlighted in blue
- User avatar + initials at bottom

---

## Page: Login (`/login`)

```
+----------------------------------------------+
|                                              |
|              SHIP                            |
|         Project Management                   |
|                                              |
|     +----------------------------------+     |
|     |  Email                           |     |
|     |  [alice@ship.dev               ] |     |
|     +----------------------------------+     |
|     +----------------------------------+     |
|     |  Password                        |     |
|     |  [********                     ] |     |
|     +----------------------------------+     |
|     +----------------------------------+     |
|     |           [ Login ]              |     |
|     +----------------------------------+     |
|                                              |
+----------------------------------------------+
```

- Centered card on gray-950 background
- Blue "Login" button full-width
- Error message appears below button on failure

---

## Page: Dashboard (`/`)

```
+------------------+----------------------------------------------+
|   SIDEBAR        |  Dashboard                                   |
|                  |                                              |
|   [Dashboard]*   |  My Current Sprint                          |
|   Wiki           |  ------------------------------------------ |
|   Programs       |  Title         Status       Priority  Week  |
|   Projects       |  ------------------------------------------ |
|   Teams          |  Auth tokens   In Progress  High      Wk 3 |
|                  |  Fix login     To Do        Medium    Wk 3 |
|                  |  API docs      In Review    Low       Wk 3 |
|                  |  ------------------------------------------ |
|                  |                                              |
|   ----------     |  (Shows only issues assigned to current user |
|   Settings       |   in the current/latest week)               |
|   [AC] Alice     |                                              |
+------------------+----------------------------------------------+
```

---

## Page: Wiki List (`/wiki`)

```
+------------------+----------------------------------------------+
|   SIDEBAR        |  Wiki                         [+ New Wiki]  |
|                  |                                              |
|   Dashboard      |  ------------------------------------------ |
|   [Wiki]*        |  Title                Created    Updated    |
|   Programs       |  ------------------------------------------ |
|   Projects       |  Engineering Handbook  Mar 1     Mar 28     |
|   Teams          |  Onboarding Guide     Mar 5     Mar 20     |
|                  |  API Standards        Mar 10    Mar 25     |
|                  |  ------------------------------------------ |
|                  |                                              |
|   ----------     |  (Click row → /wiki/:id)                    |
|   Settings       |                                              |
|   [AC] Alice     |                                              |
+------------------+----------------------------------------------+
```

---

## Page: Wiki View (`/wiki/:id`)

```
+------------------+----------------------------------+-----------+
|   SIDEBAR        |  Wiki Title                      | Metadata  |
|                  |  ============================    |           |
|   Dashboard      |                                  | Creator:  |
|   [Wiki]*        |  WIKI DOCUMENT CONTENT BODY      | Alice     |
|   Programs       |                                  |           |
|   Projects       |  Lorem ipsum dolor sit amet,     | Created:  |
|   Teams          |  consectetur adipiscing elit.     | Mar 1     |
|                  |  Sed do eiusmod tempor incididunt|           |
|                  |  ut labore et dolore magna       | Updated:  |
|                  |  aliqua.                         | Mar 28    |
|                  |                                  |           |
|                  |  [Edit] [Delete]                 | Maint:    |
|   ----------     |                                  | Bob       |
|   Settings       |                                  |           |
|   [AC] Alice     |                                  |           |
+------------------+----------------------------------+-----------+
```

- Main content area: 70% width
- Metadata sidebar: 30% width, light gray bg
- Edit button opens inline editing of title + body
- Delete button shows confirmation modal

---

## Page: Programs List (`/programs`)

```
+------------------+----------------------------------------------+
|   SIDEBAR        |  Programs                    [+ New Program] |
|                  |                                              |
|   Dashboard      |  ------------------------------------------ |
|   Wiki           |  Title       Owner    Projects  Updated     |
|   [Programs]*    |  ------------------------------------------ |
|   Projects       |  Platform    Alice    2         Mar 28      |
|   Teams          |  Product     Bob      1         Mar 25      |
|                  |  ------------------------------------------ |
|                  |                                              |
|   ----------     |  (Click row → /programs/:id)                |
|   Settings       |                                              |
|   [AC] Alice     |                                              |
+------------------+----------------------------------------------+
```

---

## Page: Program View (`/programs/:id`)

```
+------------------+----------------------------------------------+
|   SIDEBAR        |  Platform                                    |
|                  |  [Overview]  [Issues]  [Projects]  [Weeks]   |
|   Dashboard      |  ============================================|
|   Wiki           |                                              |
|   [Programs]*    |  --- OVERVIEW TAB (default) ---              |
|   Projects       |                                              |
|   Teams          |  PROGRAM DESCRIPTION BODY                    |
|                  |                                              |
|                  |  Lorem ipsum dolor sit amet...               |
|                  |                                              |
|                  |  [Edit] [Delete]                             |
|                  |                                              |
|   ----------     |  Owner: Alice    Approver: Bob               |
|   Settings       |  Created: Mar 1  Updated: Mar 28            |
|   [AC] Alice     |                                              |
+------------------+----------------------------------------------+
```

### Program View — Issues Tab

```
|  Platform                                                       |
|  [Overview]  [Issues]*  [Projects]  [Weeks]                     |
|  ============================================================== |
|                                                                 |
|  Title          Status        Priority  Project     Updated     |
|  ----------------------------------------------------------------|
|  Auth tokens    In Progress   High      Auth Redes  Mar 28      |
|  Fix login      To Do         Medium    Auth Redes  Mar 25      |
|  API rate lim   Backlog       Low       API Gateway Mar 20      |
|  ... (all issues across all projects in this program)           |
|  ----------------------------------------------------------------|
|  (Click row → /issues/:id)                                      |
```

### Program View — Projects Tab

```
|  Platform                                                       |
|  [Overview]  [Issues]  [Projects]*  [Weeks]                     |
|  ============================================================== |
|                                                                 |
|  Title          Owner    Issues  ICE Score  Updated             |
|  ----------------------------------------------------------------|
|  Auth Redesign  Alice    3       19         Mar 28              |
|  API Gateway    Alice    3       38         Mar 25              |
|  ----------------------------------------------------------------|
|  (Click row → /projects/:id)                                    |
```

---

## Page: Projects List (`/projects`)

```
+------------------+----------------------------------------------+
|   SIDEBAR        |  Projects                    [+ New Project] |
|                  |                                              |
|   Dashboard      |  ------------------------------------------ |
|   Wiki           |  Title          Owner   Issues  ICE  Prog   |
|   Programs       |  ------------------------------------------ |
|   [Projects]*    |  Auth Redesign  Alice   3       19   Platfm |
|   Teams          |  Dashboard v2   Bob     3       48   Prodct |
|                  |  API Gateway    Alice   3       38   Platfm |
|                  |  ------------------------------------------ |
|                  |                                              |
|   ----------     |  (Click row → /projects/:id)                |
|   Settings       |                                              |
|   [AC] Alice     |                                              |
+------------------+----------------------------------------------+
```

---

## Page: Project View (`/projects/:id`)

```
+------------------+----------------------------------------------+
|   SIDEBAR        |  Auth Redesign                               |
|                  |  [Overview]  [Issues]  [Weeks]  [Retro]      |
|   Dashboard      |  ============================================|
|   Wiki           |                                              |
|   Programs       |  --- OVERVIEW TAB (default) ---              |
|   [Projects]*    |                                              |
|   Teams          |  PROJECT DESCRIPTION BODY                    |
|                  |                                              |
|                  |  Modernize authentication flow with          |
|                  |  session-based auth and CSRF protection.     |
|                  |                                              |
|                  |  [Edit] [Delete]                             |
|                  |                                              |
|   ----------     |  Owner: Alice  Program: Platform             |
|   Settings       |  Impact: 4  Confidence: 3  Ease: 2          |
|   [AC] Alice     |  ICE Score: 19  Design Approved: No         |
+------------------+----------------------------------------------+
```

### Project View — Issues Tab

```
|  Auth Redesign                                                  |
|  [Overview]  [Issues]*  [Weeks]  [Retro]                        |
|  ============================================================== |
|                                                                 |
|  Title          Status        Priority  Assignee  Week         |
|  ----------------------------------------------------------------|
|  Auth tokens    In Progress   High      Alice     Wk 2         |
|  Fix login      To Do         Medium    Bob       Wk 3         |
|  Session mgmt   Backlog       Low       —         —            |
|  ----------------------------------------------------------------|
|  (Click row → /issues/:id)                                      |
|                                       [+ New Issue]             |
```

### Project View — Weeks Tab

```
|  Auth Redesign                                                  |
|  [Overview]  [Issues]  [Weeks]*  [Retro]                        |
|  ============================================================== |
|                                                                 |
|  Week 2 (Current)                                               |
|  ----------------------------------------------------------------|
|  Title          Status        Priority  Assignee               |
|  Auth tokens    In Progress   High      Alice                  |
|  ----------------------------------------------------------------|
|                                                                 |
|  Week 3 (Upcoming)                                              |
|  ----------------------------------------------------------------|
|  Fix login      To Do         Medium    Bob                    |
|  ----------------------------------------------------------------|
|                                                                 |
|  (Groups issues by week_number, shows current + upcoming)       |
```

---

## Page: Issue View (`/issues/:id`)

```
+------------------+----------------------------------+-----------+
|   SIDEBAR        |  Auth tokens                     | Metadata  |
|                  |  ============================    |           |
|   Dashboard      |                                  | Status:   |
|   Wiki           |  ISSUE DOCUMENT CONTENT BODY     |[In Prog ▼]|
|   Programs       |                                  |           |
|   [Projects]*    |  Implement token-based auth      | Priority: |
|   Teams          |  with refresh token rotation.    | [High   ▼]|
|                  |  Need to handle edge cases       |           |
|                  |  around expired sessions.        | Assignee: |
|                  |                                  | [Alice  ▼]|
|                  |  [Edit] [Delete]                 |           |
|                  |                                  | Estimate: |
|   ----------     |                                  | [4 hrs   ]|
|   Settings       |                                  |           |
|   [AC] Alice     |                                  | Week: 2   |
|                  |                                  | Project:  |
|                  |                                  | Auth Red. |
|                  |                                  | Program:  |
|                  |                                  | Platform  |
|                  |                                  |           |
|                  |                                  | Created:  |
|                  |                                  | Mar 15    |
|                  |                                  | Updated:  |
|                  |                                  | Mar 28    |
+------------------+----------------------------------+-----------+
```

- Status and Priority are dropdown selects (editable inline)
- Assignee is a user dropdown
- Week is a number input
- Edit button toggles title + body editing
- Delete shows confirmation

---

## Page: Teams (`/teams`)

```
+------------------+----------------------------------------------+
|   SIDEBAR        |  Team                                        |
|                  |                                              |
|   Dashboard      |  ------------------------------------------ |
|   Wiki           |  Name           Email            Role       |
|   Programs       |  ------------------------------------------ |
|   Projects       |  Alice Chen     alice@ship.dev   Engineer   |
|   [Teams]*       |  Bob Martinez   bob@ship.dev     PM         |
|                  |  ------------------------------------------ |
|                  |                                              |
|   ----------     |                                              |
|   Settings       |                                              |
|   [AC] Alice     |                                              |
+------------------+----------------------------------------------+
```

---

## Create/Edit Modals

### New Wiki / Program / Project
```
+------------------------------------------+
|  Create New [Wiki/Program/Project]       |
|                                          |
|  Title: [_________________________]      |
|  Body:  [_________________________]      |
|         [_________________________]      |
|         [_________________________]      |
|                                          |
|  (Type-specific fields below)            |
|  Owner: [Select user ▼]   (prog/proj)   |
|  Program: [Select ▼]      (proj only)   |
|                                          |
|          [Cancel]  [Create]              |
+------------------------------------------+
```

### New Issue
```
+------------------------------------------+
|  Create New Issue                        |
|                                          |
|  Title: [_________________________]      |
|  Body:  [_________________________]      |
|                                          |
|  Status:   [Needs Triage ▼]             |
|  Priority: [No Priority ▼]             |
|  Assignee: [Select user ▼]             |
|  Project:  [Select project ▼]           |
|  Week:     [__ ]                         |
|  Estimate: [__ ] hours                   |
|                                          |
|          [Cancel]  [Create]              |
+------------------------------------------+
```

---

## Styling Notes

- **Background:** gray-950 (dark theme)
- **Cards/Tables:** gray-900 with gray-800 borders
- **Text:** gray-100 (primary), gray-400 (secondary)
- **Active/Selected:** blue-500 for highlights, blue-600 for active sidebar
- **Buttons:** blue-600 primary, gray-700 secondary, red-600 destructive
- **Status badges:** green (done), blue (in progress), yellow (in review), gray (backlog/todo), red (cancelled/urgent)
- **Font:** System font stack (Inter if available, otherwise sans-serif)
- **Table rows:** hover:bg-gray-800, click navigates to detail view
