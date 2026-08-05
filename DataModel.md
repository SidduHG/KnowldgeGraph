# CKG — Data Model Reference

---

## Overview

The knowledge graph is stored in MySQL across 5 tables.
Two tables are the graph itself (`nodes`, `edges`).
Two tables drive incremental indexing (`file_hashes`, `file_deps`).
One table is an audit log (`index_runs`).

```
file_hashes ──────────┐
                       ↓
file_deps ──→ dirty-set propagation ──→ nodes + edges (graph)
                                              ↑
index_runs ───────────────────────────────────┘
```

---

## Table: `nodes`

Every symbol in the codebase is a node.

| Column           | Type          | Description                                      |
|------------------|---------------|--------------------------------------------------|
| `id`             | VARCHAR(64)   | SHA-256 of `file_path::qualified_name::type` (32 hex chars) |
| `type`           | ENUM          | Symbol type — see Node Types below               |
| `name`           | VARCHAR(512)  | Short name e.g. `validate_token`                 |
| `qualified_name` | VARCHAR(1024) | Full dotted path e.g. `auth.service.UserService.validate_token` |
| `file_path`      | TEXT          | Absolute path to source file                     |
| `start_line`     | INT           | First line of the symbol definition              |
| `end_line`       | INT           | Last line of the symbol definition               |
| `signature`      | TEXT          | Function signature or class declaration          |
| `docstring`      | TEXT          | First docstring/JSDoc comment                    |
| `language`       | VARCHAR(32)   | `python` \| `typescript` \| `javascript`         |
| `created_at`     | TIMESTAMP     | Auto                                             |
| `updated_at`     | TIMESTAMP     | Auto-updated on upsert                           |

### Node Types

| Type       | Description                              | Example                     |
|------------|------------------------------------------|-----------------------------|
| `FILE`     | A source file                            | `src/auth/service.py`       |
| `MODULE`   | Package directory with init/index        | `src/auth/`                 |
| `CLASS`    | Class, interface, struct, enum           | `class UserService`         |
| `FUNCTION` | Top-level function                       | `def validate_token()`      |
| `METHOD`   | Function belonging to a class            | `UserService.login()`       |
| `VARIABLE` | Module or class-level variable/constant  | `MAX_RETRIES = 3`           |
| `TYPE`     | Type alias, typedef, interface           | `type UserId = string`      |

### Indexes

```sql
INDEX idx_nodes_name       (name(255))
INDEX idx_nodes_file_path  (file_path(512))
INDEX idx_nodes_type       (type)
FULLTEXT INDEX ft_nodes_search (name, signature)
```

---

## Table: `edges`

Every relationship between nodes is an edge.

| Column      | Type    | Description                                       |
|-------------|---------|---------------------------------------------------|
| `id`        | VARCHAR(64) | SHA-256 of `source_id->target_id::type`       |
| `source_id` | VARCHAR(64) | FK → `nodes.id`                               |
| `target_id` | VARCHAR(64) | FK → `nodes.id`                               |
| `type`      | ENUM    | Relationship type — see Edge Types below          |
| `metadata`  | JSON    | Extra data (call arguments, import alias, etc.)   |
| `file_path` | TEXT    | File where this relationship was found            |
| `created_at`| TIMESTAMP | Auto                                            |

### Edge Types

| Type       | Direction              | Meaning                                      |
|------------|------------------------|----------------------------------------------|
| `DEFINES`  | FILE → symbol          | File contains this symbol                    |
| `IMPORTS`  | FILE → FILE            | File imports from another file               |
| `CALLS`    | FUNCTION/METHOD → FUNCTION/METHOD | Direct invocation             |
| `INHERITS` | CLASS → CLASS          | `extends` or `implements` a parent           |
| `CONTAINS` | CLASS → METHOD/VARIABLE| Class owns this member                       |
| `USES`     | FUNCTION → VARIABLE/TYPE | Reads or references a symbol               |
| `EXPORTS`  | FILE → symbol          | Publicly exported from this module           |

### Indexes

```sql
INDEX idx_edges_source (source_id)
INDEX idx_edges_target (target_id)
INDEX idx_edges_type   (type)
```

Cascade deletes: when a node is deleted, all its edges are deleted too.

---

## Table: `file_hashes`

Drives the "only re-index changed files" logic.

| Column        | Type          | Description                          |
|---------------|---------------|--------------------------------------|
| `path`        | VARCHAR(1024) | Absolute file path (PK)              |
| `sha256`      | VARCHAR(64)   | SHA-256 hex digest of file content   |
| `file_size`   | BIGINT        | File size in bytes                   |
| `language`    | VARCHAR(32)   | Detected language                    |
| `analyzed_at` | TIMESTAMP     | When this file was last indexed      |

### How It Works

1. On any index run, compute `SHA-256` of each file.
2. Compare against `file_hashes.sha256`.
3. If **match** → skip entirely (zero work).
4. If **different or missing** → add to dirty set → re-parse → update hash.

This means restarting the indexer after a reboot does zero work if no
files changed. The whole repo re-index takes milliseconds on restart.

---

## Table: `file_deps`

The import dependency graph. Powers dirty-set propagation.

| Column     | Type          | Description                             |
|------------|---------------|-----------------------------------------|
| `importer` | VARCHAR(1024) | File that has the import statement      |
| `importee` | VARCHAR(1024) | File being imported                     |

PK is `(importer, importee)`.

### How Propagation Works

When file `B` changes:
1. `B` is added to dirty set.
2. Query: `SELECT importer FROM file_deps WHERE importee = 'B'`
3. All importers of `B` (e.g. `A`, `C`, `D`) are also added to dirty set.
4. Reason: `A` may hold edges to symbols in `B` that have changed
   (renamed function, removed class, changed signature).

Only **one hop** is propagated — not recursive. Recursive propagation
can cascade the entire codebase and is almost never necessary.

---

## Table: `index_runs`

Audit log. Every call to `POST /index` creates a row here.

| Column          | Type      | Description                               |
|-----------------|-----------|-------------------------------------------|
| `id`            | INT AUTO  | Run ID                                    |
| `run_type`      | ENUM      | `FULL` \| `INCREMENTAL`                   |
| `repo_path`     | TEXT      | Repository that was indexed               |
| `files_scanned` | INT       | Total files examined                      |
| `files_indexed` | INT       | Files actually re-parsed (were in dirty set) |
| `files_skipped` | INT       | Files skipped (hash matched)              |
| `nodes_created` | INT       | Nodes upserted                            |
| `edges_created` | INT       | Edges upserted                            |
| `duration_ms`   | INT       | Wall-clock time of the run                |
| `status`        | ENUM      | `RUNNING` \| `COMPLETED` \| `FAILED`      |
| `error_message` | TEXT      | Error detail if status is FAILED          |
| `started_at`    | TIMESTAMP | When run began                            |
| `completed_at`  | TIMESTAMP | When run finished                         |

---

## Entity Relationship Summary

```
FILE ──DEFINES──► CLASS ──CONTAINS──► METHOD
  │                  │                  │
  │               INHERITS            CALLS
  │                  ↓                  ↓
  └──IMPORTS──► FILE     CLASS     FUNCTION
  │
  └──DEFINES──► FUNCTION ──CALLS──► FUNCTION
  │
  └──DEFINES──► VARIABLE

file_hashes: one row per FILE (not a graph node — operational only)
file_deps:   mirrors IMPORTS edges but at the file level (path strings)
```

---

## Node ID Generation

Node IDs are deterministic — the same symbol always gets the same ID:

```python
import hashlib

def node_id(file_path: str, qualified_name: str, node_type: str) -> str:
    raw = f"{file_path}::{qualified_name}::{node_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

This means upserts are safe — re-indexing a file that didn't change its
symbols produces identical IDs and just updates timestamps, no duplicates.

---

## Query Patterns (used by MCP resolvers)

```sql
-- get_function: find symbol by name
SELECT * FROM nodes
WHERE name = 'validate_token'
AND type IN ('FUNCTION','METHOD','CLASS');

-- get_callers: who calls this function?
SELECT n.* FROM edges e
JOIN nodes n ON n.id = e.source_id
WHERE e.target_id = '<node_id>'
AND e.type = 'CALLS';

-- get_callees: what does this function call?
SELECT n.* FROM edges e
JOIN nodes n ON n.id = e.target_id
WHERE e.source_id = '<node_id>'
AND e.type = 'CALLS';

-- get_file_map: all symbols in a file
SELECT * FROM nodes
WHERE file_path = '/repo/src/auth/service.py'
ORDER BY start_line;

-- search_symbol: fuzzy name search
SELECT * FROM nodes
WHERE name LIKE '%validate%'
ORDER BY CHAR_LENGTH(name) LIMIT 20;

-- get_related: import graph for a file
SELECT importee FROM file_deps WHERE importer = '/repo/src/auth/service.py';
SELECT importer FROM file_deps WHERE importee = '/repo/src/auth/service.py';
```