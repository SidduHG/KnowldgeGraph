# Phase 1: Implementation Steps

Step 1 — Schema first. Before any parsing, define and lock your SQLite schema: the four tables (nodes, edges, file_hashes, file_deps) plus a virtual FTS5 table for full-text symbol search. Add indexes on file_path, name, and type columns. Schema migrations go in a versioned migrations/ folder from day one — you will need them.

Step 2 — Language detection. On startup, walk the repo and build a map of which languages are present by extension. This determines which tree-sitter grammars to load. Store this in config.json inside .ckg/. Don't parse every file type — only the ones you have grammar support for.

Step 3 — Initial full scan. Walk all detected source files. For each file, compute SHA-256. Query file_hashes — if the hash matches, skip. If missing or different, add to the dirty set. On a fresh repo this puts everything in dirty. On a re-run after a reboot it puts almost nothing in dirty.

Step 4 — Dirty set propagation. For every file in the dirty set, look up file_deps WHERE importee = that_file. Every importer found gets added to the dirty set too (one hop only — don't recurse, it's almost never necessary and can cascade your entire graph). This ensures callers of changed symbols don't hold stale edges.

Step 5 — Parse and extract. For each file in the dirty set: delete all existing nodes and edges where file_path = this_file. Run tree-sitter. Walk the AST with language-specific queries to extract nodes (functions, classes, variables) and edges (calls, imports, inherits). Batch insert everything.

Step 6 — Update hash registry. After successfully parsing and storing a file, write the new SHA-256 and timestamp to file_hashes. Do this in the same SQLite transaction as the node/edge insert — so a crash mid-write leaves the file in dirty state on next run.

Step 7 — Start the file watcher. After the initial scan completes, start chokidar (Node) or watchdog (Python) watching the repo. On any create, change, or unlink event, run the same pipeline from Step 3 onward with just that file. The watcher should debounce rapid saves (300ms) to avoid thrashing on format-on-save.
