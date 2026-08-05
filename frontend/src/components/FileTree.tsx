import React, { useState, useMemo } from "react";
import type { NodeOut } from "../types/graph";
import { NODE_COLORS } from "../types/graph";

/* ── Types ────────────────────────────────────────────────────────────────── */
interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
  symbols: NodeOut[];
}

interface Props {
  nodes: NodeOut[];
  selectedNode: NodeOut | null;
  onSelect: (node: NodeOut) => void;
}

/* ── Icons ────────────────────────────────────────────────────────────────── */
const ICON: Record<string, string> = {
  FILE: "📄", MODULE: "📦", CLASS: "🟣", FUNCTION: "🟢",
  METHOD: "🔵", VARIABLE: "🟡", TYPE: "🔶",
};

const FOLDER_OPEN = "📂";
const FOLDER_CLOSED = "📁";

/* ── Build Tree ───────────────────────────────────────────────────────────── */
function buildTree(nodes: NodeOut[]): TreeNode {
  const root: TreeNode = { name: "/", path: "", isDir: true, children: [], symbols: [] };
  const dirMap = new Map<string, TreeNode>();
  dirMap.set("", root);

  // Group symbols by file_path
  const fileGroups = new Map<string, NodeOut[]>();
  for (const n of nodes) {
    const fp = n.file_path;
    if (!fileGroups.has(fp)) fileGroups.set(fp, []);
    fileGroups.get(fp)!.push(n);
  }

  // For each file, build directory chain + attach symbols
  for (const [filePath, symbols] of fileGroups) {
    // Normalize: find consistent prefix to strip
    const parts = filePath.replace(/\\/g, "/").split("/").filter(Boolean);

    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const partPath = parts.slice(0, i + 1).join("/");
      const isLastPart = i === parts.length - 1;

      if (!dirMap.has(partPath)) {
        const child: TreeNode = {
          name: parts[i],
          path: partPath,
          isDir: !isLastPart,
          children: [],
          symbols: isLastPart ? symbols.filter(s => s.type !== "FILE") : [],
        };
        dirMap.set(partPath, child);
        current.children.push(child);
      }
      current = dirMap.get(partPath)!;

      // If this is the file node, attach non-FILE symbols
      if (isLastPart && current.symbols.length === 0) {
        current.symbols = symbols.filter(s => s.type !== "FILE");
      }
    }
  }

  // Sort: directories first, then files alphabetically
  const sortChildren = (node: TreeNode) => {
    node.children.sort((a, b) => {
      if (a.isDir && !b.isDir) return -1;
      if (!a.isDir && b.isDir) return 1;
      return a.name.localeCompare(b.name);
    });
    node.children.forEach(sortChildren);
  };
  sortChildren(root);

  return root;
}

/* ── Collapse shared prefix directories ──────────────────────────────────── */
function collapseTree(node: TreeNode): TreeNode {
  // If a directory has exactly one child that is also a directory, merge them
  if (node.isDir && node.children.length === 1 && node.children[0].isDir) {
    const child = node.children[0];
    const merged: TreeNode = {
      name: node.name ? `${node.name}/${child.name}` : child.name,
      path: child.path,
      isDir: true,
      children: child.children,
      symbols: child.symbols,
    };
    return collapseTree(merged);
  }
  return {
    ...node,
    children: node.children.map(collapseTree),
  };
}

/* ── Tree Node Component ──────────────────────────────────────────────────── */
const TreeItem: React.FC<{
  node: TreeNode;
  depth: number;
  selectedNode: NodeOut | null;
  onSelect: (node: NodeOut) => void;
  expandedPaths: Set<string>;
  onToggle: (path: string) => void;
}> = ({ node, depth, selectedNode, onSelect, expandedPaths, onToggle }) => {
  const isExpanded = expandedPaths.has(node.path);
  const indent = depth * 14;

  if (node.isDir) {
    const hasContent = node.children.length > 0 || node.symbols.length > 0;
    return (
      <div>
        <div
          onClick={() => hasContent && onToggle(node.path)}
          style={{
            paddingLeft: indent + 8, paddingRight: 8,
            paddingTop: 3, paddingBottom: 3,
            cursor: hasContent ? "pointer" : "default",
            display: "flex", alignItems: "center", gap: 5,
            fontSize: 12, color: "var(--text)",
            borderRadius: 4,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <span style={{ fontSize: 11, width: 14, textAlign: "center", flexShrink: 0 }}>
            {isExpanded ? FOLDER_OPEN : FOLDER_CLOSED}
          </span>
          <span style={{ fontWeight: 500, opacity: 0.85 }}>{node.name}</span>
          <span style={{
            fontSize: 9, color: "var(--text-muted)", marginLeft: "auto",
          }}>
            {node.children.length > 0 && `${node.children.length}`}
          </span>
        </div>
        {isExpanded && (
          <div>
            {node.children.map((child) => (
              <TreeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedNode={selectedNode}
                onSelect={onSelect}
                expandedPaths={expandedPaths}
                onToggle={onToggle}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // File node
  return (
    <div>
      <div
        onClick={() => onToggle(node.path)}
        style={{
          paddingLeft: indent + 8, paddingRight: 8,
          paddingTop: 3, paddingBottom: 3,
          cursor: "pointer",
          display: "flex", alignItems: "center", gap: 5,
          fontSize: 12, color: "var(--text)",
          borderRadius: 4,
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        <span style={{ fontSize: 11, width: 14, textAlign: "center", flexShrink: 0 }}>
          {isExpanded ? "📄" : "📄"}
        </span>
        <span style={{ fontWeight: 500 }}>{node.name}</span>
        {node.symbols.length > 0 && (
          <span style={{
            fontSize: 9, color: "var(--text-muted)", marginLeft: "auto",
            background: "var(--bg)", padding: "1px 5px", borderRadius: 8,
          }}>
            {node.symbols.length}
          </span>
        )}
      </div>
      {isExpanded && node.symbols.length > 0 && (
        <div style={{ paddingLeft: indent + 22 }}>
          {node.symbols
            .sort((a, b) => (a.start_line ?? 0) - (b.start_line ?? 0))
            .map((sym) => {
              const color = NODE_COLORS[sym.type] ?? "#888780";
              const active = selectedNode?.id === sym.id;
              return (
                <div
                  key={sym.id}
                  onClick={(e) => { e.stopPropagation(); onSelect(sym); }}
                  style={{
                    paddingTop: 2, paddingBottom: 2,
                    paddingLeft: 6, paddingRight: 6,
                    cursor: "pointer",
                    display: "flex", alignItems: "center", gap: 5,
                    fontSize: 11, borderRadius: 3,
                    background: active ? color + "18" : "transparent",
                    borderLeft: active ? `2px solid ${color}` : "2px solid transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!active) e.currentTarget.style.background = color + "0a";
                  }}
                  onMouseLeave={(e) => {
                    if (!active) e.currentTarget.style.background = "transparent";
                  }}
                >
                  <span style={{ fontSize: 10, flexShrink: 0 }}>
                    {ICON[sym.type] ?? "•"}
                  </span>
                  <span style={{
                    color: active ? color : "var(--text)",
                    fontWeight: active ? 600 : 400,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  }}>
                    {sym.name}
                  </span>
                  {sym.start_line && (
                    <span style={{
                      fontSize: 9, color: "var(--text-muted)", marginLeft: "auto",
                      flexShrink: 0,
                    }}>
                      L{sym.start_line}
                    </span>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
};

/* ── Main Component ───────────────────────────────────────────────────────── */
export const FileTree: React.FC<Props> = ({ nodes, selectedNode, onSelect }) => {
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());

  const tree = useMemo(() => {
    const raw = buildTree(nodes);
    return collapseTree(raw);
  }, [nodes]);

  // Auto-expand root
  React.useEffect(() => {
    const initial = new Set<string>();
    initial.add(tree.path);
    // Expand first 2 levels
    for (const child of tree.children) {
      initial.add(child.path);
    }
    setExpandedPaths(initial);
  }, [tree]);

  const handleToggle = (path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const expandAll = () => {
    const all = new Set<string>();
    const walk = (n: TreeNode) => {
      all.add(n.path);
      n.children.forEach(walk);
    };
    walk(tree);
    setExpandedPaths(all);
  };

  const collapseAll = () => {
    setExpandedPaths(new Set([tree.path]));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", gap: 4, padding: "6px 8px",
        borderBottom: "1px solid var(--border)",
      }}>
        <button
          onClick={expandAll}
          style={{
            flex: 1, padding: "3px 6px", fontSize: 10,
            background: "var(--bg)", border: "1px solid var(--border)",
            borderRadius: 4, color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          ▾ Expand
        </button>
        <button
          onClick={collapseAll}
          style={{
            flex: 1, padding: "3px 6px", fontSize: 10,
            background: "var(--bg)", border: "1px solid var(--border)",
            borderRadius: 4, color: "var(--text-muted)", cursor: "pointer",
          }}
        >
          ▸ Collapse
        </button>
      </div>

      {/* Tree */}
      <div style={{ overflowY: "auto", flex: 1, padding: "4px 0" }}>
        {tree.children.map((child) => (
          <TreeItem
            key={child.path}
            node={child}
            depth={0}
            selectedNode={selectedNode}
            onSelect={onSelect}
            expandedPaths={expandedPaths}
            onToggle={handleToggle}
          />
        ))}
        {tree.children.length === 0 && (
          <div style={{
            padding: 20, fontSize: 12, color: "var(--text-muted)",
            textAlign: "center",
          }}>
            No files indexed yet
          </div>
        )}
      </div>
    </div>
  );
};
