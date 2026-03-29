# Framework Cheat Sheet

Use these patterns. Do NOT use outdated alternatives.

## React 18

```tsx
// Entry point (main.tsx) — use createRoot, NOT ReactDOM.render
import { createRoot } from 'react-dom/client';
import App from './App';

createRoot(document.getElementById('root')!).render(<App />);
```

- `react-dom/client` is the correct import (NOT `react-dom`)
- `createRoot` replaces `ReactDOM.render` (removed in React 18)

## React Router v6

```tsx
// Use Routes + Route with element prop
import { BrowserRouter, Routes, Route } from 'react-router-dom';

<BrowserRouter>
  <Routes>
    <Route path="/" element={<WorkspacePage />} />
    <Route path="/programs/:id" element={<ProgramPage />} />
  </Routes>
</BrowserRouter>
```

- **DO NOT** use `Switch` (that's v5, removed in v6)
- **DO NOT** use `component={Page}` prop (that's v5)
- Use `element={<Page />}` instead
- `BrowserRouter` in ONE place only (App.tsx OR main.tsx, never both)
- Use `useParams()` to read URL params, `useNavigate()` for programmatic navigation
- Use `<Link to="/path">` for navigation links

## Express

```typescript
import express from 'express';
const app = express();

// ALWAYS add JSON middleware for POST/PUT bodies
app.use(express.json());

// Error handling middleware (MUST be last)
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});
```

## sql.js

```typescript
import initSqlJs from 'sql.js';

const SQL = await initSqlJs();
const db = new SQL.Database();

// db.exec() returns array of result sets, NOT objects
// Result format: [{ columns: ['id', 'title', ...], values: [['1', 'Hello', ...], ...] }]

// ALWAYS null-check before accessing values
const result = db.exec('SELECT * FROM documents WHERE type = ?', [type]);
const rows = result[0]?.values || [];  // Empty array if no results

// ALWAYS map to typed objects with camelCase
const documents = rows.map(row => ({
  id: row[0],
  type: row[1],
  title: row[2],
  content: row[3],
  parentId: row[4],       // SQL column: parent_id
  status: row[5],
  priority: row[6],
  createdAt: row[7],      // SQL column: created_at
  updatedAt: row[8],      // SQL column: updated_at
}));

// For parameterized queries use prepare/bind/get
const stmt = db.prepare('SELECT * FROM documents WHERE id = ?');
stmt.bind([id]);
if (stmt.step()) {
  const row = stmt.get();
  // row is an array, map to object same as above
}
stmt.free();
```

## Vite + React Setup

Required files for Vite to work:

**1. index.html** (in package root, NOT in src/):
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>App</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

**2. vite.config.ts:**
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

**3. API client must use relative URLs:**
```typescript
// CORRECT — goes through Vite proxy, no CORS
const BASE_URL = '/api';

// WRONG — causes CORS errors
const BASE_URL = 'http://localhost:3001/api';
```

## TailwindCSS v3

**tailwind.config.js:**
```javascript
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
};
```

**src/index.css:**
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

Import in main.tsx: `import './index.css';`

## npm Workspaces

```bash
# Install a package in a specific workspace
npm install express -w packages/api
npm install react -w packages/web

# Do NOT cd into subdirectories and run npm install there
# Do NOT use npm install -g (permission issues)

# Run a script in a workspace
npm run dev -w packages/web
```
