import React, { useState } from "react";
import type { IndexStatus } from "../types/graph";

interface Props {
  indexStatus: IndexStatus | null;
  loading: boolean;
  watching: boolean;
  onIndex: (path: string) => void;
  onStartWatch: (path: string) => void;
  onStopWatch: () => void;
}

export const IndexPanel: React.FC<Props> = ({
  indexStatus, loading, watching, onIndex, onStartWatch, onStopWatch,
}) => {
  const [path, setPath] = useState("/repo/OneDrive/Desktop/Desktop/KnowldgeGraph");

  const pct = indexStatus?.pct ?? 0;
  const status = indexStatus?.status ?? "idle";

  const btnStyle = (color: string, disabled = false): React.CSSProperties => ({
    padding: "7px 14px", borderRadius: 6, border: "none",
    background: disabled ? "var(--border)" : color,
    color: disabled ? "var(--text-muted)" : "#fff",
    fontSize: 12, fontWeight: 500, cursor: disabled ? "not-allowed" : "pointer",
    transition: "opacity .15s",
  });

  return (
    <div style={{ padding: "16px", borderBottom: "1px solid var(--border)" }}>
      <p style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".07em",
        color: "var(--text-muted)", margin: "0 0 10px" }}>Indexer</p>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="/absolute/path/to/repo"
          style={{
            flex: 1, padding: "7px 10px", borderRadius: 6, fontSize: 12,
            background: "var(--surface)", border: "1px solid var(--border)",
            color: "var(--text)", fontFamily: "var(--font-mono)",
          }}
        />
        <button
          style={btnStyle("#185FA5", loading || !path.trim())}
          disabled={loading || !path.trim()}
          onClick={() => onIndex(path.trim())}
        >
          Index
        </button>
      </div>

      {status === "running" && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between",
            fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
            <span>Indexing… {indexStatus?.files_done}/{indexStatus?.files_total} files</span>
            <span>{pct}%</span>
          </div>
          <div style={{ height: 4, borderRadius: 2, background: "var(--border)" }}>
            <div style={{
              height: "100%", borderRadius: 2, background: "#0F6E56",
              width: `${pct}%`, transition: "width .4s ease",
            }} />
          </div>
        </div>
      )}

      {status === "completed" && indexStatus && (
        <div style={{ fontSize: 11, color: "#0F6E56", marginBottom: 12 }}>
          ✓ {indexStatus.files_done} files · {indexStatus.nodes_created} nodes
          · {indexStatus.edges_created} edges · {indexStatus.elapsed_ms}ms
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{
          width: 7, height: 7, borderRadius: "50%",
          background: watching ? "#0F6E56" : "#BA7517",
          boxShadow: watching ? "0 0 0 2px #0F6E5640" : "none",
        }} />
        <span style={{ fontSize: 11, color: "var(--text-muted)", flex: 1 }}>
          {watching ? "Watcher running — auto-indexing on save" : "Watcher stopped"}
        </span>
        {watching ? (
          <button style={btnStyle("#993556")} onClick={onStopWatch}>Stop</button>
        ) : (
          <button
            style={btnStyle("#BA7517", !path.trim())}
            disabled={!path.trim()}
            onClick={() => onStartWatch(path.trim())}
          >
            Watch
          </button>
        )}
      </div>
    </div>
  );
};
