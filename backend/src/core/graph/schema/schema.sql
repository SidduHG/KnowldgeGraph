-- ============================================================
-- CKG - Code Knowledge Graph  |  Migration 001 - Initial Schema (SQLite)
-- ============================================================

-- SQLite requires enabling foreign keys per connection, but we define them here.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS nodes (
  id             TEXT NOT NULL PRIMARY KEY,
  type           TEXT NOT NULL CHECK(type IN ('FILE','MODULE','CLASS','FUNCTION','METHOD','VARIABLE','TYPE')),
  name           TEXT NOT NULL,
  qualified_name TEXT DEFAULT NULL,
  file_path      TEXT NOT NULL,
  start_line     INTEGER DEFAULT NULL,
  end_line       INTEGER DEFAULT NULL,
  signature      TEXT DEFAULT NULL,
  docstring      TEXT DEFAULT NULL,
  language       TEXT DEFAULT NULL,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);

-- SQLite FTS5 Virtual Table for Full-Text Search
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
  name, 
  signature, 
  content='nodes', 
  content_rowid='id'
);

-- Triggers to keep FTS5 table in sync with nodes table
CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
  INSERT INTO nodes_fts(rowid, name, signature) VALUES (new.id, new.name, new.signature);
END;
CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
  INSERT INTO nodes_fts(nodes_fts, rowid, name, signature) VALUES('delete', old.id, old.name, old.signature);
END;
CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
  INSERT INTO nodes_fts(nodes_fts, rowid, name, signature) VALUES('delete', old.id, old.name, old.signature);
  INSERT INTO nodes_fts(rowid, name, signature) VALUES (new.id, new.name, new.signature);
END;

CREATE TABLE IF NOT EXISTS edges (
  id          TEXT NOT NULL PRIMARY KEY,
  source_id   TEXT NOT NULL,
  target_id   TEXT NOT NULL,
  type        TEXT NOT NULL CHECK(type IN ('DEFINES','IMPORTS','CALLS','INHERITS','CONTAINS','USES','EXPORTS')),
  metadata    TEXT DEFAULT NULL, -- SQLite doesn't have native JSON type, JSON is stored as TEXT
  file_path   TEXT DEFAULT NULL,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
  FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);

CREATE TABLE IF NOT EXISTS file_hashes (
  path        TEXT NOT NULL PRIMARY KEY,
  sha256      TEXT NOT NULL,
  file_size   INTEGER DEFAULT 0,
  language    TEXT DEFAULT NULL,
  analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fh_sha256 ON file_hashes(sha256);

CREATE TABLE IF NOT EXISTS file_deps (
  importer    TEXT NOT NULL,
  importee    TEXT NOT NULL,
  PRIMARY KEY (importer, importee)
);

CREATE INDEX IF NOT EXISTS idx_fd_importee ON file_deps(importee);

CREATE TABLE IF NOT EXISTS index_runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_type        TEXT NOT NULL CHECK(run_type IN ('FULL','INCREMENTAL')),
  repo_path       TEXT NOT NULL,
  files_scanned   INTEGER DEFAULT 0,
  files_indexed   INTEGER DEFAULT 0,
  files_skipped   INTEGER DEFAULT 0,
  nodes_created   INTEGER DEFAULT 0,
  edges_created   INTEGER DEFAULT 0,
  duration_ms     INTEGER DEFAULT NULL,
  status          TEXT DEFAULT 'RUNNING' CHECK(status IN ('RUNNING','COMPLETED','FAILED')),
  error_message   TEXT DEFAULT NULL,
  started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at    DATETIME DEFAULT NULL
);
