export interface NodeOut {
  id: string;
  type: string;
  name: string;
  qualified_name: string | null;
  file_path: string;
  start_line: number | null;
  end_line: number | null;
  signature: string | null;
  docstring: string | null;
  language: string | null;
}

export interface EdgeOut {
  id: string;
  source_id: string;
  target_id: string;
  type: string;
  file_path: string | null;
}

export interface StatsResponse {
  total_files: number;
  total_nodes: number;
  total_edges: number;
  node_types: Record<string, number>;
  edge_types: Record<string, number>;
  last_run: Record<string, unknown> | null;
}

export interface IndexStatus {
  status: string;
  run_type: string;
  repo_path: string;
  files_total: number;
  files_done: number;
  files_skipped: number;
  nodes_created: number;
  edges_created: number;
  errors: number;
  elapsed_ms: number;
  pct: number;
  error_message: string;
}

export type NodeType =
  | "FILE" | "MODULE" | "CLASS" | "FUNCTION"
  | "METHOD" | "VARIABLE" | "TYPE";

export type EdgeType =
  | "DEFINES" | "IMPORTS" | "CALLS" | "INHERITS"
  | "CONTAINS" | "USES" | "EXPORTS";

export const NODE_COLORS: Record<string, string> = {
  FILE:     "#888780",
  MODULE:   "#888780",
  CLASS:    "#185FA5",
  FUNCTION: "#0F6E56",
  METHOD:   "#0F6E56",
  VARIABLE: "#BA7517",
  TYPE:     "#993556",
};

export const EDGE_COLORS: Record<string, string> = {
  DEFINES:  "#888780",
  IMPORTS:  "#888780",
  CALLS:    "#0F6E56",
  INHERITS: "#185FA5",
  CONTAINS: "#888780",
  USES:     "#BA7517",
  EXPORTS:  "#993556",
};
