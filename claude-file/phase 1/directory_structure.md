# Directory Structure

```text
ckg/ <- project root
|
├── .ckg/ <- runtime data, gitignored, one per repo
|   ├── graph.db <- SQLite database
|   └── config.json <- detected languages, ignore patterns
|
├── src/
|   ├── core/ <- shared by both phases
|   |   ├── parser/
|   |   |   ├── languages/ <- one file per language grammar
|   |   |   └── extractor/ <- walks AST -> nodes + edges
|   |   ├── graph/
|   |   |   ├── schema/ <- schema.sql + migrations/
|   |   |   ├── nodes/ <- node type definitions + constants
|   |   |   └── edges/ <- edge type definitions + constants
|   |   └── store/ <- all SQLite access lives here
|   |       ├── hash_registry/ <- read/write file_hashes table
|   |       ├── node_store/ <- upsert + delete nodes
|   |       ├── edge_store/ <- upsert + delete edges
|   |       └── dep_index/ <- read/write file_deps + reverse lookup
|   |
|   ├── indexer/ Phase 1
|   |   ├── scanner/ <- walks repo, detects languages, lists files
|   |   ├── dirty_set/ <- hash comparison -> builds dirty set
|   |   ├── propagator/ <- reverse dep lookup -> expands dirty set
|   |   ├── builder/ <- orchestrates: dirty -> parse -> store
|   |   └── watcher/ <- chokidar / watchdog, debounced
|
├── config/
|   └── ckg.config.json <- ignore patterns, language overrides
|
└── tests/
    ├── fixtures/ <- tiny sample repos, one per language
    ├── unit/ <- test parser, extractor, hash logic individually
    └── integration/ <- test full scan -> query end-to-end
```
