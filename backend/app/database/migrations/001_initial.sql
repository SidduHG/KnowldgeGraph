-- ============================================================
-- CKG - Code Knowledge Graph  |  Migration 001 - Initial Schema (MySQL)
-- ============================================================

CREATE TABLE IF NOT EXISTS nodes (
  id             VARCHAR(64) NOT NULL PRIMARY KEY,
  type           ENUM('FILE','MODULE','CLASS','FUNCTION','METHOD','VARIABLE','TYPE') NOT NULL,
  name           VARCHAR(255) NOT NULL,
  qualified_name VARCHAR(512) DEFAULT NULL,
  file_path      TEXT NOT NULL,
  start_line     INT DEFAULT NULL,
  end_line       INT DEFAULT NULL,
  signature      TEXT DEFAULT NULL,
  docstring      TEXT DEFAULT NULL,
  source_snippet TEXT DEFAULT NULL,
  language       VARCHAR(32) DEFAULT NULL,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_nodes_name (name),
  INDEX idx_nodes_type (type),
  FULLTEXT INDEX idx_nodes_fts (name, signature)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS edges (
  id          VARCHAR(64) NOT NULL PRIMARY KEY,
  source_id   VARCHAR(64) NOT NULL,
  target_id   VARCHAR(64) NOT NULL,
  type        ENUM('DEFINES','IMPORTS','CALLS','INHERITS','CONTAINS','USES','EXPORTS') NOT NULL,
  metadata    JSON DEFAULT NULL,
  file_path   TEXT DEFAULT NULL,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_edges_source (source_id),
  INDEX idx_edges_target (target_id),
  INDEX idx_edges_type (type),
  FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
  FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS file_hashes (
  path        VARCHAR(768) NOT NULL,
  sha256      VARCHAR(64) NOT NULL,
  file_size   INT DEFAULT 0,
  language    VARCHAR(32) DEFAULT NULL,
  analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (path(191)),
  INDEX idx_fh_sha256 (sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS file_deps (
  importer    VARCHAR(760) NOT NULL,
  importee    VARCHAR(760) NOT NULL,
  PRIMARY KEY (importer(380), importee(380)),
  INDEX idx_fd_importee (importee(380))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS index_runs (
  id              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  run_type        ENUM('FULL','INCREMENTAL') NOT NULL,
  repo_path       TEXT NOT NULL,
  files_scanned   INT DEFAULT 0,
  files_indexed   INT DEFAULT 0,
  files_skipped   INT DEFAULT 0,
  nodes_created   INT DEFAULT 0,
  edges_created   INT DEFAULT 0,
  duration_ms     INT DEFAULT NULL,
  status          ENUM('RUNNING','COMPLETED','FAILED') DEFAULT 'RUNNING',
  error_message   TEXT DEFAULT NULL,
  started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at    DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
