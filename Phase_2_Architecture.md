# Code Knowledge Graph - Phase 2 & Async Architecture

## Final Directory Structure
```text
backend/
├── main.py                     # FastAPI entry point, lifespan events & routing connections
├── requirements.txt            # Locked explicit dependencies (pydantic-core, tree-sitter, etc.)
├── app/
│   ├── config.py               # Pydantic Settings layer (MySQL properties, ignores)
│   ├── api/
│   │   ├── schemas.py          # Unified Pydantic models (IndexRequest, NodeOut, EdgeOut)
│   │   └── routes/             # REST Endpoints
│   │       ├── index.py        # API router to trigger background/foreground index runs 
│   │       ├── graph.py        # Search and graph queries (Nodes, edges, file maps)
│   │       └── status.py       # Observability endpoints (Health & DB Checksum Stats)
│   ├── core/
│   │   ├── builder.py          # Extracts nodes using Parsers and saves to DB (GraphBuilder)
│   │   ├── indexer.py          # Orchestrates Scanners, Builders, and Dependency Maps (IndexerService)
│   │   ├── scanner.py          # Safely walks the file system generating physical SHAs
│   │   └── watcher.py          # Subscribes to watchdog events for formatting/save reactivity
│   ├── database/
│   │   └── connection.py       # MySQL / Async Engine integration (`db_session`)
│   ├── parser/                 
│   │   ├── base.py             # Defines abstract Parser logic & Type nodes
│   │   ├── registry.py         # Singleton lazy-loader ensuring memory efficiency
│   │   └── languages/          
│   │       ├── python_parser.py     # C-bound Tree-sitter Python Language extraction 
│   │       └── typescript_parser.py # JS/TS/TSX Tree walker mapper identifying Classes/Methods
│   ├── store/                  
│   │   ├── dep_store.py        # Relies on Graph dependencies to find cross-file dirty updates
│   │   ├── edge_store.py       # Edge relationships database writer (DEFINES, CALLS, INHERITS)
│   │   ├── hash_store.py       # Tracks structural file states to skip unaffected files
│   │   └── node_store.py       # Upserts the actual Abstract Syntax Nodes into SQL
│   └── utils/
│       └── logger.py           # Standardized application console logging
└── tests/
    ├── unit/
    │   └── test_parsers.py     # Base validation checking extracted variables and functions
    └── integration/
        └── test_indexer.py     # Boot tests ensuring logic creates DB relationships properly
```

## Implementation Highlights

1. **Tree-Sitter Language Engines Installed:**
   We installed and bound `tree-sitter==0.23.2` along with `tree-sitter-python==0.23.4`, providing native blazing-fast file parsing mapped to our `base.py` node definitions!

2. **Clean Dependency Locking:**
   All exact specifications inside you latest requirements text were seamlessly updated, clearing any cross-dependency issues with `pydantic-core`.

3. **Rest API Mapped! (Phase 2 Component):**
   A full suite of REST endpoints `(GET /graph/nodes, POST /index, GET /status)` are properly separated and handled by your asynchronous schema system inside `app.api.routes`.

4. **Async Service Isolation:**
   We strictly relocated raw SQLite code and transitioned entirely to SQL Alchemy's Async engine logic (e.g., `async with db_session():`) making the app perfectly responsive.
