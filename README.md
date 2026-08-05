<p align="center">
  <strong>◈ CKG</strong><br>
  <em>Code Knowledge Graph</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/react-18.3-61dafb?style=flat-square" />
  <img src="https://img.shields.io/badge/fastapi-0.115-009688?style=flat-square" />
  <img src="https://img.shields.io/badge/mysql-8.0-4479A1?style=flat-square" />
  <img src="https://img.shields.io/badge/MCP-v1.0-8B5CF6?style=flat-square" />
</p>

---

**CKG** is a production-ready **Code Knowledge Graph** that parses any codebase into a structured graph of symbols (classes, functions, methods, variables) and relationships (defines, imports, calls, inherits), then exposes that graph through a visual dashboard **and** an MCP (Model Context Protocol) server so AI coding agents can query codebase structure without scanning raw files — saving **~95% of token budget per query**.

## ✨ Features

### 🔍 Intelligent Code Parsing
- **Multi-language** — Python and TypeScript/TSX via tree-sitter AST parsing
- **Symbol extraction** — classes, functions, methods, variables, types
- **Relationship mapping** — DEFINES, CONTAINS, IMPORTS, CALLS, INHERITS, USES, EXPORTS
- **Incremental indexing** — dirty-set propagation for efficient re-indexing

### 🌐 Interactive Graph Visualization
- **Force-directed layout** — D3 physics simulation with glow effects
- **Zoom-to-node** — click a node to zoom in, see its details, click again to zoom out
- **Edge type filters** — toggle DEFINES, IMPORTS, CALLS, etc. to reduce visual noise
- **Live search** — fuzzy symbol search with sidebar results
- **Auto-reload** — graph updates automatically when new data is indexed
- **Node legend** — color-coded by type (FILE, CLASS, FUNCTION, METHOD, VARIABLE, TYPE)

### 🤖 MCP Server (AI Agent Integration)
- **13 specialized tools** for surgical context retrieval
- **Hard token budget** — every response is counted with `tiktoken` and truncated
  at the configured cap (default 400) before being returned
- **Semantic search** — natural-language symbol lookup via a local
  `all-MiniLM-L6-v2` embedding model ("find the function that refreshes auth tokens")
- **Diff-aware context** — `get_diff_context` returns only the symbols whose
  lines changed in a git ref + their 1-hop blast radius (drop-in replacement
  for pasting a raw diff into your agent)
- **Dual transport** — stdio (Claude CLI) + HTTP REST (Cursor, Codex, Gemini)
- **Auto-discovery** — `/config` endpoint generates tool definitions for any AI agent

### 🔄 Per-Repo Isolation
- Index any repository — data automatically replaces when switching repos
- Old graph data is cleared before indexing a new codebase
- No data mixing between projects

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Network                    │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Frontend    │  │   Backend    │  │   MCP Server     │  │
│  │  React + Vite │  │   FastAPI    │  │   FastAPI        │  │
│  │  :5173 (dev)  │──│   :8000      │  │   :8001          │  │
│  │               │  │              │  │                  │  │
│  │  • Graph View │  │  • Indexer   │  │  • 10 Tools      │  │
│  │  • Sidebar    │  │  • Parser    │  │  • stdio adapter │  │
│  │  • StatsBar   │  │  • Scanner   │  │  • HTTP API      │  │
│  │  • Filters    │  │  • Watcher   │  │  • Formatters    │  │
│  └──────────────┘  └──────┬───────┘  └────────┬─────────┘  │
│                           │                    │            │
│                    ┌──────┴────────────────────┴──────┐     │
│                    │          MySQL 8.0               │     │
│                    │          :3307                   │     │
│                    │  nodes │ edges │ file_hashes │   │     │
│                    │  file_deps │ index_runs      │   │     │
│                    └─────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with WSL2 on Windows)
- [Node.js](https://nodejs.org/) ≥ 18 (for frontend dev server)

### 1. Clone & Start Services

```bash
git clone https://github.com/your-username/KnowldgeGraph.git
cd KnowldgeGraph

# First-time build (takes ~3–5 min, includes sentence-transformers ~500MB)
docker compose build

# Start all backend services (MySQL + Backend + MCP Server)
docker compose up -d

# Check everything is healthy
docker compose ps
curl http://localhost:8001/health
# → {"ok": true, "version": "2.2.0", "tools_count": 13, "semantic_available": true}
```

To rebuild after code changes:
```bash
docker compose up -d --build
```

To view logs:
```bash
docker compose logs -f mcp_server
docker compose logs -f backend
```

To tear everything down (keeps the MySQL volume):
```bash
docker compose down
```

### 2. Start Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 3. Index a Repository

Open `http://localhost:5173` in your browser and enter the Docker-mapped path:

```
/repo/OneDrive/Desktop/Desktop/YourProject
```

> **Path Mapping**: Your `%USERPROFILE%` directory is mounted to `/repo` inside Docker.
> So `C:\Users\you\Projects\MyApp` becomes `/repo/Projects/MyApp`.

Click **Index** and watch the graph build in real-time.

### 4. (Optional) Build the semantic index

Semantic search needs embeddings to be precomputed once per indexed repo:

```bash
curl -X POST http://localhost:8001/tools/reindex_embeddings
# → {"ok": true, "embedded": 1842, "model": "sentence-transformers/all-MiniLM-L6-v2"}
```

Re-run this after every full re-index. Incremental changes don't need it unless
symbol signatures or docstrings move.

---

## 🧰 MCP Tools Reference

The MCP server exposes **13 tools** optimized for minimal token consumption:

| Tool | Description | ~Tokens |
|------|-------------|---------|
| `get_stats` | Repo overview — file/node/edge counts, language breakdown, hotspot files | 89 |
| `get_context` | File-level context — all symbols, signatures, line ranges | 144 |
| `get_definition` | Exact symbol definition lookup — file path, line, signature | 18 |
| `search_symbol` | Fuzzy symbol name search across the entire graph | 50–100 |
| `search_semantic` 🆕 | Natural-language symbol search via local embeddings | 60–150 |
| `get_diff_context` 🆕 | Symbols touched by `git diff <ref>` + 1-hop blast radius | 100–300 |
| `reindex_embeddings` 🆕 | Rebuild the semantic index (run once after full index) | 20 |
| `get_file_map` | Full file structure — tree of all symbols in a file | 80 |
| `get_related` | Connected symbols — what this symbol defines/calls/imports | 30 |
| `get_hierarchy` | Class inheritance tree | 20 |
| `get_callers` | Reverse lookup — who calls/references this symbol | 20 |
| `get_callees` | What a function calls | 20 |
| `get_function` | Function/class details by name | 40 |

### Example: Using with Claude CLI

**Option A — HTTP transport (recommended, zero local setup):**
```bash
# All deps live in Docker; Claude just calls the HTTP API.
claude mcp add --transport http ckg http://localhost:8001

# Verify registration
claude mcp list
```

**Option B — stdio transport (via `.mcp.json`):**
```bash
# Requires the MCP server's Python deps installed on the host:
pip install -r mcp_server/requirements.txt

# Then:
claude mcp add-from-file .mcp.json
```

Now Claude can query your codebase:
- *"What classes are in config.py?"* → `get_context`
- *"Where is IndexerService defined?"* → `get_definition`
- *"Show me the repo structure"* → `get_stats`
- *"Find the function that validates JWT tokens"* → `search_semantic`
- *"What did I change on this branch?"* → `get_diff_context`

### Example: Using with HTTP API

```bash
# Repo overview
curl -X POST http://localhost:8001/tools/get_stats \
  -H "Content-Type: application/json" -d '{}'

# Search for a symbol
curl -X POST http://localhost:8001/tools/search_symbol \
  -H "Content-Type: application/json" -d '{"query": "Settings"}'

# Get file context (saves ~95% tokens vs reading raw file)
curl -X POST http://localhost:8001/tools/get_context \
  -H "Content-Type: application/json" -d '{"file_path": "config.py"}'
```

---

## 📁 Project Structure

```
KnowldgeGraph/
├── docker-compose.yml          # Orchestrates all 3 services
├── .mcp.json                   # Claude CLI MCP configuration
│
├── backend/                    # FastAPI backend (indexer + API)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI app entry
│       ├── config.py           # Pydantic settings
│       ├── api/
│       │   ├── routes/
│       │   │   ├── index.py    # POST /index, GET /index/status
│       │   │   ├── graph.py    # GET /graph/nodes, /graph/edges
│       │   │   └── status.py   # GET /status (stats)
│       │   └── schemas.py      # Pydantic request/response models
│       ├── core/
│       │   ├── indexer.py      # IndexerService (per-repo, non-blocking)
│       │   ├── builder.py      # GraphBuilder (AST → nodes/edges)
│       │   └── scanner.py      # RepoScanner (file discovery)
│       ├── parser/
│       │   ├── registry.py     # Language → parser mapping
│       │   ├── base.py         # ParseResult dataclass
│       │   └── languages/
│       │       ├── python_parser.py
│       │       └── typescript_parser.py
│       ├── store/              # Data access layer
│       │   ├── node_store.py
│       │   ├── edge_store.py
│       │   ├── hash_store.py
│       │   └── dep_store.py
│       ├── database/
│       │   ├── connection.py   # Async SQLAlchemy engine
│       │   └── migrations/
│       │       └── 001_initial.sql
│       └── watcher/
│           └── file_watcher.py # Watchdog-based file watcher
│
├── mcp_server/                 # MCP Server (AI agent interface)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── config.py           # MCP settings
│       ├── database.py         # Async DB connection
│       ├── tools/
│       │   └── resolvers.py    # 10 tool implementations
│       ├── formatters/
│       │   └── response.py     # Token-budgeted output formatting
│       └── adapters/
│           ├── claude_stdio.py # stdio transport (Claude CLI)
│           └── http_api.py     # HTTP REST transport
│
└── frontend/                   # React dashboard
    ├── package.json
    ├── vite.config.ts          # Dev server + API proxy
    └── src/
        ├── App.tsx             # Main app layout
        ├── main.tsx            # Entry + global CSS
        ├── api/
        │   └── client.ts       # Axios HTTP client
        ├── hooks/
        │   └── useAppStore.ts  # Zustand global state
        ├── types/
        │   └── graph.ts        # TypeScript interfaces
        └── components/
            ├── GraphView.tsx   # Force-directed graph (React Flow + D3)
            ├── StatsBar.tsx    # File/Node/Edge counters
            ├── IndexPanel.tsx  # Index trigger UI
            ├── Sidebar.tsx     # Symbol search + list
            └── NodeDetail.tsx  # Selected node detail panel
```

---

## ⚙️ Configuration

### Backend Environment (`backend/.env`)
```env
APP_NAME=CKG - Code Knowledge Graph
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=ckg_user
MYSQL_PASSWORD=ckg_password
MYSQL_DATABASE=ckg
DEBUG=false
```

### MCP Server Environment (`mcp_server/.env`)
```env
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_USER=ckg_user
MYSQL_PASSWORD=ckg_password
MYSQL_DATABASE=ckg
MODE=http
PORT=8001
```

---

## 🔌 Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Frontend (dev) | `5173` | Vite dev server with HMR |
| Backend API | `8000` | FastAPI — indexer + graph API |
| MCP Server | `8001` | MCP tools — AI agent interface |
| MySQL | `3307` | Database (mapped from container's 3306) |

---

## 🗃️ Data Model

```sql
nodes       — id, type, name, qualified_name, file_path, start_line, end_line,
              signature, docstring, language
edges       — id, source_id, target_id, type, file_path
file_hashes — file_path (PK), sha256, language, indexed_at
file_deps   — source_file, target_file
index_runs  — id, run_type, status, repo_path, files_scanned, nodes_created, ...
```

**Node types**: `FILE`, `CLASS`, `FUNCTION`, `METHOD`, `VARIABLE`, `TYPE`
**Edge types**: `DEFINES`, `CONTAINS`, `IMPORTS`, `CALLS`, `INHERITS`, `USES`, `EXPORTS`

---

## 🧪 API Quick Reference

```bash
# Health check
GET  /status/health

# Repository stats
GET  /status

# Trigger full index
POST /index                     {"repo_path": "/repo/path/to/repo"}

# Index status (poll during indexing)
GET  /index/status

# Reset stuck indexer
POST /index/reset

# List nodes (with optional filters)
GET  /graph/nodes?type=CLASS&limit=100

# Search nodes by name
GET  /graph/nodes/search?q=Config&limit=20

# List edges
GET  /graph/edges?limit=500

# File map (all symbols + edges for a file)
GET  /graph/file?path=/repo/path/to/file.py
```

---

## 🛠️ Development

### Run Backend Locally (without Docker)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run MCP Server Locally
```bash
cd mcp_server
pip install -r requirements.txt

# HTTP mode
MODE=http python -m uvicorn app.adapters.http_api:app --port 8001

# stdio mode (for Claude CLI)
python app/adapters/claude_stdio.py
```

### Rebuild Containers
```bash
docker compose build
docker compose up -d
```

---

## 📄 License

MIT

---

<p align="center">
  Built with ❤️ using FastAPI, React, tree-sitter, and D3.js
</p>
