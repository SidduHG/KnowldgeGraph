# CKG — Code Knowledge Graph
## Master Plan + Implementation Guide

---

## What This Is

A persistent, incrementally-updated knowledge graph of your codebase,
served to AI agents (Claude Code, Codex, Gemini, Cursor) as structured
tool calls — so they spend tokens on reasoning, not on reading files.

**Core insight:** Instead of feeding 50,000 tokens of raw code into an
AI context window, you ask the graph "what does `validate_token` do?"
and get back 80 tokens. The graph does the navigation; the AI does the work.

---

## Folder Structure

```
ckg/
│
├── backend/                        ← Phase 1: Indexer + REST API (Python/FastAPI)
│   ├── app/
│   │   ├── main.py                 ← FastAPI app entry point
│   │   ├── config.py               ← All settings via .env
│   │   ├── database/
│   │   │   ├── connection.py       ← SQLAlchemy async engine + session
│   │   │   └── migrations/
│   │   │       └── 001_initial.sql ← MySQL schema (run once)
│   │   ├── core/
│   │   │   ├── scanner.py          ← Walks repo, collects files + hashes
│   │   │   ├── builder.py          ← parse → resolve → upsert nodes/edges
│   │   │   └── indexer.py          ← Orchestrates full/incremental runs
│   │   ├── parser/
│   │   │   ├── base.py             ← Abstract BaseParser + ParseResult types
│   │   │   ├── registry.py         ← Maps file extension → parser instance
│   │   │   └── languages/
│   │   │       ├── python_parser.py     ← tree-sitter Python
│   │   │       └── typescript_parser.py ← tree-sitter TypeScript/JS
│   │   ├── store/
│   │   │   ├── hash_store.py       ← file_hashes table CRUD + SHA-256 diff
│   │   │   ├── dep_store.py        ← file_deps table + reverse dep propagation
│   │   │   ├── node_store.py       ← nodes table CRUD
│   │   │   └── edge_store.py       ← edges table CRUD
│   │   ├── watcher/
│   │   │   └── file_watcher.py     ← watchdog + debounce → incremental index
│   │   ├── api/
│   │   │   ├── schemas.py          ← Pydantic request/response models
│   │   │   └── routes/
│   │   │       ├── index.py        ← POST /index, GET /index/status, /watch
│   │   │       ├── status.py       ← GET /status/health, GET /status
│   │   │       └── graph.py        ← GET /graph/nodes, /edges, /file, /search
│   │   └── utils/
│   │       └── logger.py           ← Structured logging setup
│   ├── requirements.txt
│   └── .env.example
│
├── mcp_server/                     ← Phase 2: AI Agent tool server
│   ├── app/
│   │   ├── config.py               ← Mode (claude/http/both), MySQL, token budget
│   │   ├── database.py             ← Same DB, read-only connection
│   │   ├── tools/
│   │   │   └── resolvers.py        ← 6 pure SQL resolvers (no side effects)
│   │   ├── formatters/
│   │   │   └── response.py         ← Token-budgeted text formatter (≤400 tokens)
│   │   └── adapters/
│   │       ├── claude_stdio.py     ← MCP stdio transport for Claude Code
│   │       └── http_api.py         ← FastAPI REST for Codex/Gemini/Cursor
│   └── requirements.txt
│
├── frontend/                       ← Visual graph explorer (React + React Flow)
│   ├── src/
│   │   ├── main.tsx                ← Entry point + global CSS vars
│   │   ├── App.tsx                 ← Root layout
│   │   ├── types/graph.ts          ← Shared types + color maps
│   │   ├── api/client.ts           ← Axios client wrapping backend REST
│   │   ├── hooks/useAppStore.ts    ← Zustand global state
│   │   └── components/
│   │       ├── StatsBar.tsx        ← Top stats strip
│   │       ├── IndexPanel.tsx      ← Index + watch control UI
│   │       ├── Sidebar.tsx         ← Search + node list
│   │       ├── GraphView.tsx       ← React Flow canvas
│   │       └── NodeDetail.tsx      ← Right panel: selected node details
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
│
├── docker-compose.yml              ← MySQL + backend + mcp_server + frontend
├── DATA_MODEL.md                   ← Graph schema reference
└── PLAN.md                         ← This file
```

---

## Data Model (Quick Reference)

See `DATA_MODEL.md` for the full schema. Summary:

| Table         | Purpose                                        |
|---------------|------------------------------------------------|
| `nodes`       | Every symbol: FILE, CLASS, FUNCTION, METHOD... |
| `edges`       | Relationships: DEFINES, CALLS, IMPORTS...      |
| `file_hashes` | SHA-256 per file — drives skip/re-index logic  |
| `file_deps`   | Import graph — drives dirty-set propagation    |
| `index_runs`  | Audit log of every index run                   |

---

## Phase 1 — Build & Test Order

Complete each step, verify it works, then move to the next.
Do not skip ahead.

### Step 1 — MySQL up

```bash
# start MySQL (or use docker-compose)
docker compose up -d mysql

# create DB + user
mysql -u root -p
  CREATE DATABASE ckg CHARACTER SET utf8mb4;
  CREATE USER 'ckg_user'@'%' IDENTIFIED BY 'ckg_password';
  GRANT ALL ON ckg.* TO 'ckg_user'@'%';
  FLUSH PRIVILEGES;
```

**Verify:** `mysql -u ckg_user -p ckg -e "SHOW TABLES;"` → empty result, no error.

---

### Step 2 — Backend up

```bash
cd backend
cp .env.example .env           # edit MYSQL_* and REPO_PATH
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Verify:** `curl http://localhost:8000/status/health`
Expected: `{"ok":true,"version":"1.0.0","db":"ok"}`

The migration runs automatically on startup — check logs for:
`✓ Database schema ready`

---

### Step 3 — Run first index

```bash
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/absolute/path/to/any/python/project"}'
```

Poll until done:
```bash
watch -n1 'curl -s http://localhost:8000/index/status | python3 -m json.tool'
```

**Verify:** status becomes `completed`, nodes_created > 0.
Then check MySQL:
```sql
SELECT type, COUNT(*) FROM nodes GROUP BY type;
SELECT type, COUNT(*) FROM edges GROUP BY type;
```

---

### Step 4 — Start watcher

```bash
curl -X POST http://localhost:8000/index/watch \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/your/repo", "action": "start"}'
```

Now edit any `.py` or `.ts` file in the repo and save.
**Verify:** within 1–2 seconds, `/index/status` shows an incremental run completed.

---

### Step 5 — CLI

```bash
cd cli
npm install
npm run build          # compiles TypeScript → dist/

node dist/index.js status
node dist/index.js index /your/repo
node dist/index.js search MyClass
node dist/index.js watch start /your/repo
```

**Verify:** `ckg status` shows correct counts matching MySQL.

---

### Step 6 — Frontend

```bash
cd frontend
npm install
npm run dev            # starts on http://localhost:5173
```

Open browser → you should see the graph canvas with nodes visible.
**Verify:** search for a symbol → it highlights in the sidebar and graph.

---

### Step 7 — Smoke test the graph data

Run these SQL queries against your indexed repo.
Each should return results:

```sql
-- All functions in one file
SELECT name, start_line, signature
FROM nodes
WHERE file_path LIKE '%your_file.py%'
AND type = 'FUNCTION';

-- Call graph: who calls what
SELECT n1.name AS caller, n2.name AS callee
FROM edges e
JOIN nodes n1 ON n1.id = e.source_id
JOIN nodes n2 ON n2.id = e.target_id
WHERE e.type = 'CALLS'
LIMIT 20;

-- Import graph
SELECT importer, importee FROM file_deps LIMIT 10;

-- Hash registry
SELECT path, sha256, analyzed_at FROM file_hashes LIMIT 5;
```

If all 4 queries return data → Phase 1 is complete. ✓

---

## Phase 2 — MCP Server (after Phase 1 is verified)

Only start this after the graph data looks correct in MySQL.

### Step 1 — Start MCP HTTP server

```bash
cd mcp_server
pip install -r requirements.txt

# Start HTTP mode (Codex/Gemini/Cursor)
MODE=http uvicorn app.adapters.http_api:app --port 8001
```

**Verify:** `curl http://localhost:8001/health` → `{"ok":true}`

---

### Step 2 — Test tools manually

```bash
# search_symbol
curl -X POST http://localhost:8001/tools/search_symbol \
  -H "Content-Type: application/json" \
  -d '{"query": "validate"}'

# get_file_map
curl -X POST http://localhost:8001/tools/get_file_map \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/your/repo/main.py"}'

# get_callers
curl -X POST http://localhost:8001/tools/get_callers \
  -H "Content-Type: application/json" \
  -d '{"name": "process_request"}'
```

**Verify:** each returns `{"tool":"...","text":"...","tokens_est":N}`
The `text` field is what gets sent to the AI agent.

---

### Step 3 — Connect Claude Code

```bash
# Run once — Claude Code remembers this
claude mcp add ckg python mcp_server/app/adapters/claude_stdio.py
```

Then in any Claude Code session:
```
> search_symbol: UserService
> get_callers: validate_token
> get_file_map: src/auth/service.py
```

Claude Code will use these tools automatically before reading files.

---

### Step 4 — Connect Codex

```bash
# Get the tool definitions JSON
curl http://localhost:8001/config?agent=codex
```

Copy the `tools` array into your OpenAI API call.
When Codex calls a tool, POST the arguments to
`http://localhost:8001/tools/<tool_name>` and pass back the `text` field.

---

### Step 5 — Connect Gemini

```bash
curl http://localhost:8001/config?agent=gemini
```

Use the `function_declarations` array in your `GenerativeModel(tools=...)` param.

---

### Step 6 — Connect Cursor

```bash
curl http://localhost:8001/config?agent=cursor
```

Paste the `mcp_config` block into `.cursor/mcp.json`.
Cursor will pick it up on next restart.

---

## Token Savings (Why This Matters)

| Without CKG                          | With CKG                              |
|--------------------------------------|---------------------------------------|
| Read `auth/service.py` → 2,400 tok   | `get_file_map(auth/service.py)` → 90 tok |
| Read 5 files to find a function      | `search_symbol(validate)` → 60 tok   |
| No way to know callers               | `get_callers(validate_token)` → 80 tok |
| Blind file reading: ~8,000 tok/task  | Graph navigation: ~400 tok/task       |

**Estimated 90–95% token reduction** on large repos (>50 files).

---

## Adding a New Language

1. Install the tree-sitter grammar:
   `pip install tree-sitter-go` (or rust, java, etc.)

2. Create `backend/app/parser/languages/go_parser.py`
   following the same pattern as `python_parser.py`

3. Add to `backend/app/parser/registry.py`:
   ```python
   ".go": "go"
   ```
   and add a `_load("go")` case.

4. Run `ckg index` again — the new language files
   will be in the dirty set and get parsed.

---

## Environment Variables Reference

```env
# backend/.env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=ckg_user
MYSQL_PASSWORD=ckg_password
MYSQL_DATABASE=ckg
REPO_PATH=/absolute/path/to/your/repo
DEBUG=false
WATCHER_DEBOUNCE_MS=300
MAX_FILE_SIZE_KB=512
BATCH_SIZE=50

# mcp_server/.env (same MySQL vars +)
MODE=both          # claude | http | both
PORT=8001
MAX_TOKENS_PER_RESPONSE=400
```

---

## Common Issues

**`✗ Cannot reach backend`**
→ Backend not running. Run `uvicorn app.main:app --port 8000` from `backend/`.

**`nodes_created: 0` after index**
→ Check REPO_PATH is absolute. Check supported extensions in config.
→ Run with `DEBUG=true` to see which files are being skipped.

**`tree-sitter` import error**
→ `pip install tree-sitter==0.23.2 tree-sitter-python==0.23.4 tree-sitter-typescript==0.23.2`

**Watcher not triggering**
→ Some editors write via temp file rename. Watchdog handles this, but
  check that WATCHER_DEBOUNCE_MS isn't too high (keep at 300).

**MySQL charset error**
→ Make sure DB was created with `CHARACTER SET utf8mb4`.