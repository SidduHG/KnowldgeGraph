import React from "react";
import type { NodeOut } from "../types/graph";
import { NODE_COLORS } from "../types/graph";

interface Props {
  node: NodeOut | null;
  onClose: () => void;
}

const Row: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div style={{ display: "flex", flexDirection: "column", marginBottom: 12 }}>
    <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".07em",
      color: "var(--text-muted)", marginBottom: 3 }}>{label}</span>
    <span style={{ fontSize: 12, color: "var(--text)", wordBreak: "break-all",
      fontFamily: typeof value === "string" ? "var(--font-mono)" : undefined }}>
      {value ?? <em style={{ color: "var(--text-muted)" }}>—</em>}
    </span>
  </div>
);

export const NodeDetail: React.FC<Props> = ({ node, onClose }) => {
  if (!node) return null;
  const color = NODE_COLORS[node.type] ?? "#888780";

  return (
    <div style={{
      position: "absolute", right: 0, top: 0, bottom: 0,
      width: 300, background: "var(--bg)", borderLeft: "1px solid var(--border)",
      overflowY: "auto", zIndex: 10,
    }}>
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{
          fontSize: 10, fontWeight: 600, padding: "2px 7px", borderRadius: 4,
          background: color + "22", color, textTransform: "uppercase", letterSpacing: ".06em",
        }}>{node.type}</span>
        <span style={{ fontSize: 13, fontWeight: 600, flex: 1,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {node.name}
        </span>
        <button onClick={onClose} style={{
          background: "none", border: "none", cursor: "pointer",
          color: "var(--text-muted)", fontSize: 16, lineHeight: 1,
        }}>×</button>
      </div>

      <div style={{ padding: 16 }}>
        {node.signature && (
          <div style={{
            padding: "8px 10px", borderRadius: 6, background: "var(--surface)",
            fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text)",
            marginBottom: 16, borderLeft: `3px solid ${color}`,
          }}>
            {node.signature}
          </div>
        )}
        {node.docstring && (
          <div style={{
            padding: "8px 10px", borderRadius: 6, background: "var(--surface)",
            fontSize: 12, color: "var(--text-muted)", marginBottom: 16,
            fontStyle: "italic", lineHeight: 1.6,
          }}>
            {node.docstring}
          </div>
        )}
        <Row label="Qualified name" value={node.qualified_name} />
        <Row label="File" value={node.file_path} />
        <Row label="Lines" value={node.start_line != null
          ? `${node.start_line} – ${node.end_line}` : null} />
        <Row label="Language" value={node.language} />
      </div>
    </div>
  );
};
