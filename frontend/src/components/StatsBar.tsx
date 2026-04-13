import React from "react";
import type { StatsResponse } from "../types/graph";

interface Props {
  stats: StatsResponse | null;
  watching: boolean;
}

export const StatsBar: React.FC<Props> = ({ stats, watching }) => {
  const items = [
    { label: "Files",   value: stats?.total_files  ?? "—", color: "#888780" },
    { label: "Nodes",   value: stats?.total_nodes  ?? "—", color: "#185FA5" },
    { label: "Edges",   value: stats?.total_edges  ?? "—", color: "#0F6E56" },
    { label: "Watcher", value: watching ? "live" : "off",
      color: watching ? "#0F6E56" : "#BA7517" },
  ];

  return (
    <div style={{
      display: "flex", gap: 2, padding: "0 16px",
      borderBottom: "1px solid var(--border)",
    }}>
      {items.map((it) => (
        <div key={it.label} style={{
          padding: "8px 16px",
          display: "flex", alignItems: "baseline", gap: 6,
        }}>
          <span style={{ fontSize: 18, fontWeight: 600, color: it.color,
            fontFamily: "var(--font-mono)" }}>
            {it.value.toLocaleString()}
          </span>
          <span style={{ fontSize: 11, color: "var(--text-muted)",
            textTransform: "uppercase", letterSpacing: ".06em" }}>
            {it.label}
          </span>
        </div>
      ))}
    </div>
  );
};
