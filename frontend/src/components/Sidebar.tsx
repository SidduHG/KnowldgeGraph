import React, { useState } from "react";
import type { NodeOut } from "../types/graph";
import { NODE_COLORS } from "../types/graph";

interface Props {
  nodes: NodeOut[];
  selectedNode: NodeOut | null;
  onSearch: (q: string) => void;
  onSelect: (node: NodeOut) => void;
}

export const Sidebar: React.FC<Props> = ({ nodes, selectedNode, onSearch, onSelect }) => {
  const [q, setQ] = useState("");

  const handleChange = (v: string) => {
    setQ(v);
    onSearch(v);
  };

  return (
    <div style={{
      width: 260, display: "flex", flexDirection: "column",
      borderRight: "1px solid var(--border)",
      background: "var(--surface)", flexShrink: 0,
    }}>
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)" }}>
        <input
          value={q}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Search symbols…"
          style={{
            width: "100%", padding: "7px 10px", borderRadius: 6,
            background: "var(--bg)", border: "1px solid var(--border)",
            color: "var(--text)", fontSize: 12, boxSizing: "border-box",
          }}
        />
      </div>

      <div style={{ overflowY: "auto", flex: 1 }}>
        {nodes.map((node) => {
          const color = NODE_COLORS[node.type] ?? "#888780";
          const active = selectedNode?.id === node.id;
          return (
            <div
              key={node.id}
              onClick={() => onSelect(node)}
              style={{
                padding: "8px 12px", cursor: "pointer",
                background: active ? color + "14" : "transparent",
                borderLeft: active ? `3px solid ${color}` : "3px solid transparent",
                display: "flex", flexDirection: "column", gap: 2,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                  fontSize: 9, fontWeight: 600, padding: "1px 5px", borderRadius: 3,
                  background: color + "22", color, textTransform: "uppercase",
                  letterSpacing: ".05em", flexShrink: 0,
                }}>
                  {node.type}
                </span>
                <span style={{
                  fontSize: 12, fontWeight: 500, color: "var(--text)",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                  {node.name}
                </span>
              </div>
              <span style={{
                fontSize: 10, color: "var(--text-muted)",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                paddingLeft: 2,
              }}>
                {node.file_path.split("/").slice(-2).join("/")}
                {node.start_line ? `:${node.start_line}` : ""}
              </span>
            </div>
          );
        })}
        {nodes.length === 0 && (
          <div style={{ padding: 20, fontSize: 12, color: "var(--text-muted)",
            textAlign: "center" }}>
            No symbols yet
          </div>
        )}
      </div>
    </div>
  );
};
