import React, { useEffect } from "react";
import { useAppStore } from "./hooks/useAppStore";
import { StatsBar } from "./components/StatsBar";
import { IndexPanel } from "./components/IndexPanel";
import { GraphView } from "./components/GraphView";
import { Sidebar } from "./components/Sidebar";
import { NodeDetail } from "./components/NodeDetail";

export default function App() {
  const {
    stats, indexStatus, watching, nodes, edges,
    selectedNode, loading, error,
    fetchStats, fetchIndexStatus, startIndex, startWatch, stopWatch,
    search, loadAllNodes, loadEdges, selectNode, clearError,
  } = useAppStore();

  useEffect(() => {
    fetchStats();
    fetchIndexStatus();
    loadAllNodes().then(loadEdges);
    const t = setInterval(() => { fetchStats(); fetchIndexStatus(); }, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{
      height: "100vh", display: "flex", flexDirection: "column",
      background: "var(--bg)", color: "var(--text)", fontFamily: "var(--font-sans)",
    }}>
      <div style={{
        display: "flex", alignItems: "center",
        borderBottom: "1px solid var(--border)",
        padding: "0 20px", height: 44, flexShrink: 0,
      }}>
        <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: ".04em",
          marginRight: 24, color: "var(--text)" }}>
          ◈ CKG
        </span>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
          Code Knowledge Graph
        </span>
        {loading && (
          <span style={{ marginLeft: "auto", fontSize: 11, color: "#BA7517" }}>
            ● indexing…
          </span>
        )}
        {error && (
          <span onClick={clearError} style={{ marginLeft: "auto", fontSize: 11,
            color: "#993556", cursor: "pointer" }}>
            ✗ {error}
          </span>
        )}
      </div>

      <StatsBar stats={stats} watching={watching} />

      <IndexPanel
        indexStatus={indexStatus} loading={loading} watching={watching}
        onIndex={startIndex} onStartWatch={startWatch} onStopWatch={stopWatch}
      />

      <div style={{ flex: 1, display: "flex", overflow: "hidden", position: "relative" }}>
        <Sidebar
          nodes={nodes} selectedNode={selectedNode}
          onSearch={search} onSelect={selectNode}
        />
        <GraphView nodes={nodes} edges={edges} onNodeClick={selectNode} />
        <NodeDetail node={selectedNode} onClose={() => selectNode(null)} />
      </div>
    </div>
  );
}
