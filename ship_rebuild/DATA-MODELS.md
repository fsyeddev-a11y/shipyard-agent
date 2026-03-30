# DATA-MODELS.md — Ship Database Schema

## Database: PostgreSQL

Connection: `DATABASE_URL` environment variable.

---

## Table: users

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Table: sessions

```sql
CREATE TABLE sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  last_activity TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
```

## Enum: document_type

```sql
CREATE TYPE document_type AS ENUM ('wiki', 'issue', 'program', 'project', 'week');
```

## Table: documents

The core table. ALL content types live here.

```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_type document_type NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  properties JSONB NOT NULL DEFAULT '{}',
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_documents_created_by ON documents(created_by);
CREATE INDEX idx_documents_active ON documents(document_type) WHERE deleted_at IS NULL;
```

## Table: document_associations

Links documents together (program→project, project→issue, issue→week).

```sql
CREATE TABLE document_associations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  related_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  relationship_type TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(document_id, related_id, relationship_type)
);

CREATE INDEX idx_assoc_document ON document_associations(document_id);
CREATE INDEX idx_assoc_related ON document_associations(related_id);
CREATE INDEX idx_assoc_type ON document_associations(relationship_type);
```

### Relationship Types

| relationship_type | document_id type | related_id type | Meaning |
|-------------------|-----------------|-----------------|---------|
| `program` | project | program | Project belongs to program |
| `project` | issue | project | Issue belongs to project |
| `program` | issue | program | Issue belongs to program (denormalized for fast queries) |
| `week` | issue | week | Issue assigned to week/sprint |

---

## Properties by Document Type

### Wiki Properties
```typescript
interface WikiProperties {
  maintainer_id?: string;  // UUID of user maintaining this wiki
}
```

### Program Properties
```typescript
interface ProgramProperties {
  owner_id?: string;       // UUID - responsible person
  approver_id?: string;    // UUID - accountable person
  consulted_id?: string;   // UUID - consulted person
  informed_id?: string;    // UUID - informed person
}
```

### Project Properties
```typescript
interface ProjectProperties {
  owner_id?: string;
  approver_id?: string;
  consulted_id?: string;
  informed_id?: string;
  program_id?: string;     // denormalized for easy access
  design_approved?: boolean;
  impact?: number;         // 1-5
  confidence?: number;     // 1-5
  ease?: number;           // 1-5
  ice_score?: number;      // Computed: (impact * confidence * ease) / 1.25, range 0-100
}
```

### Issue Properties
```typescript
interface IssueProperties {
  status: 'needs_triage' | 'backlog' | 'todo' | 'in_progress' | 'in_review' | 'done' | 'cancelled';
  priority: 'no_priority' | 'low' | 'medium' | 'high' | 'urgent';
  assignee_id?: string;    // UUID
  time_estimate?: number;  // hours
  project_id?: string;     // denormalized
  program_id?: string;     // denormalized
  week_number?: number;    // which sprint/week this issue is in
}
```

### Week Properties
```typescript
interface WeekProperties {
  week_number: number;
  project_id?: string;     // denormalized - which project this week belongs to
}
```

---

## ICE Score Calculation

```
ICE = (impact * confidence * ease) / 1.25
```

Where impact, confidence, ease are each 1-5. Max score: (5*5*5)/1.25 = 100.

Computed on the frontend or in a PATCH handler when any component changes.

---

## Seed Data

### Users
```sql
INSERT INTO users (id, email, password_hash, display_name) VALUES
  ('a1111111-1111-1111-1111-111111111111', 'alice@ship.dev', '$2a$10$...hash_of_password123...', 'Alice Chen'),
  ('b2222222-2222-2222-2222-222222222222', 'bob@ship.dev', '$2a$10$...hash_of_password123...', 'Bob Martinez');
```

### Wiki Documents
```sql
INSERT INTO documents (id, document_type, title, body, created_by, properties) VALUES
  ('w1000001-...', 'wiki', 'Engineering Handbook', 'Standards and practices for the engineering team...', 'a111...', '{"maintainer_id": "a111..."}'),
  ('w1000002-...', 'wiki', 'Onboarding Guide', 'Welcome to Ship! This guide covers...', 'a111...', '{"maintainer_id": "b222..."}'),
  ('w1000003-...', 'wiki', 'API Standards', 'All APIs must follow REST conventions...', 'b222...', '{"maintainer_id": "b222..."}');
```

### Programs
```sql
INSERT INTO documents (id, document_type, title, body, created_by, properties) VALUES
  ('p1000001-...', 'program', 'Platform', 'Infrastructure and developer tools program...', 'a111...', '{"owner_id": "a111...", "approver_id": "b222..."}'),
  ('p1000002-...', 'program', 'Product', 'User-facing product features program...', 'b222...', '{"owner_id": "b222...", "approver_id": "a111..."}');
```

### Projects
```sql
INSERT INTO documents (id, document_type, title, body, created_by, properties) VALUES
  ('j1000001-...', 'project', 'Auth Redesign', 'Modernize authentication flow...', 'a111...', '{"owner_id": "a111...", "program_id": "p1000001-...", "impact": 4, "confidence": 3, "ease": 2, "ice_score": 19}'),
  ('j1000002-...', 'project', 'Dashboard v2', 'New dashboard with sprint view...', 'b222...', '{"owner_id": "b222...", "program_id": "p1000002-...", "impact": 5, "confidence": 4, "ease": 3, "ice_score": 48}'),
  ('j1000003-...', 'project', 'API Gateway', 'Centralized API gateway...', 'a111...', '{"owner_id": "a111...", "program_id": "p1000001-...", "impact": 3, "confidence": 4, "ease": 4, "ice_score": 38}');
```

*Plus document_associations linking each project to its program.*

### Issues (9 total, 3 per project)
Varied statuses, priorities, assignees, and week assignments. See SPECS.md Spec 10 for exact seed SQL.

### Weeks (4 per project)
```sql
INSERT INTO documents (id, document_type, title, body, properties) VALUES
  ('wk100001-...', 'week', 'Week 1', '', '{"week_number": 1, "project_id": "j1000001-..."}'),
  ('wk100002-...', 'week', 'Week 2', '', '{"week_number": 2, "project_id": "j1000001-..."}'),
  -- ... 4 weeks per project, 12 total
```

---

## Query Patterns

### Get all issues in a program (through projects)
```sql
SELECT d.* FROM documents d
JOIN document_associations da ON d.id = da.document_id
WHERE da.related_id IN (
  SELECT da2.document_id FROM document_associations da2
  WHERE da2.related_id = $program_id AND da2.relationship_type = 'program'
)
AND d.document_type = 'issue'
AND d.deleted_at IS NULL;
```

### Get all issues in a project
```sql
SELECT d.* FROM documents d
JOIN document_associations da ON d.id = da.document_id
WHERE da.related_id = $project_id
AND da.relationship_type = 'project'
AND d.document_type = 'issue'
AND d.deleted_at IS NULL;
```

### Get issues for a specific week in a project
```sql
SELECT d.* FROM documents d
WHERE d.document_type = 'issue'
AND d.deleted_at IS NULL
AND d.properties->>'project_id' = $project_id
AND (d.properties->>'week_number')::int = $week_number;
```

### Get projects in a program
```sql
SELECT d.* FROM documents d
JOIN document_associations da ON d.id = da.document_id
WHERE da.related_id = $program_id
AND da.relationship_type = 'program'
AND d.document_type = 'project'
AND d.deleted_at IS NULL;
```
