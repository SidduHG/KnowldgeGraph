import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow, Background, Controls, MiniMap,
  type Node, type Edge, type NodeTypes,
  useNodesState, useEdgesState,
  Handle, Position, MarkerType,
  useReactFlow, ReactFlowProvider,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  forceSimulation, forceLink, forceManyBody, forceCenter,
  forceCollide, forceX, forceY,
  type SimulationNodeDatum, type SimulationLinkDatum,
} from "d3-force";

import type { NodeOut, EdgeOut } from "../types/graph";
import { NODE_COLORS, EDGE_COLORS, type EdgeType } from "../types/graph";

const EDGE_TYPES: EdgeType[] = ["DEFINES","IMPORTS","CALLS","INHERITS","CONTAINS","USES","EXPORTS"];

/* ════════════════════════════════════════════════════════════════════════════
   CONSTANTS
   ════════════════════════════════════════════════════════════════════════════ */
const TYPE_ORDER = ["FILE","MODULE","CLASS","FUNCTION","METHOD","VARIABLE","TYPE"];

const NODE_SIZE: Record<string, number> = {
  FILE: 40, MODULE: 38, CLASS: 36,
  FUNCTION: 30, METHOD: 28, VARIABLE: 22, TYPE: 24,
};

/* ════════════════════════════════════════════════════════════════════════════
   CUSTOM NODE — Glowing circle with pulsing ring on focus
   ════════════════════════════════════════════════════════════════════════════ */
function RoundNode({ data, selected }: NodeProps) {
  const raw = (data as any).raw as NodeOut;
  const focused = (data as any).focused as boolean;
  const dimmed = (data as any).dimmed as boolean;
  const color = NODE_COLORS[raw.type] ?? "#888780";
  const r = NODE_SIZE[raw.type] ?? 28;
  const label = raw.name.length > 12 ? raw.name.slice(0, 11) + "…" : raw.name;
  const opacity = dimmed ? 0.2 : 1;

  return (
    <div style={{
      width: r * 2, height: r * 2, position: "relative",
      opacity, transition: "opacity 0.35s ease",
    }}>
      {/* Pulse ring when focused */}
      {focused && (
        <div style={{
          position: "absolute", inset: -8, borderRadius: "50%",
          border: `2px solid ${color}`,
          animation: "pulse-ring 1.8s ease-out infinite",
        }} />
      )}

      {/* Main circle */}
      <div
        title={`${raw.type}: ${raw.name}\n${raw.file_path}${raw.start_line ? `:${raw.start_line}` : ""}`}
        style={{
          width: "100%", height: "100%", borderRadius: "50%",
          background: `radial-gradient(circle at 38% 32%, ${color}88 0%, ${color}33 60%, ${color}15 100%)`,
          border: `2.5px solid ${focused ? "#fff" : color}`,
          boxShadow: focused
            ? `0 0 28px ${color}cc, 0 0 60px ${color}44, inset 0 -4px 12px ${color}44`
            : `0 0 14px ${color}55, inset 0 -2px 6px ${color}33`,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          cursor: "pointer",
          transition: "box-shadow 0.25s, border-color 0.25s, transform 0.2s",
        }}
        onMouseEnter={e => {
          if (!focused) {
            e.currentTarget.style.boxShadow = `0 0 24px ${color}99, inset 0 -3px 10px ${color}44`;
            e.currentTarget.style.transform = "scale(1.12)";
          }
        }}
        onMouseLeave={e => {
          if (!focused) {
            e.currentTarget.style.boxShadow = `0 0 14px ${color}55, inset 0 -2px 6px ${color}33`;
            e.currentTarget.style.transform = "scale(1)";
          }
        }}
      >
        <span style={{
          fontSize: r > 30 ? 10 : 8, fontWeight: 700, color: "#fff",
          textAlign: "center", lineHeight: 1.15, padding: "0 4px",
          textShadow: `0 1px 4px rgba(0,0,0,0.6), 0 0 8px ${color}`,
          userSelect: "none", wordBreak: "break-word", maxWidth: r * 1.6,
        }}>
          {label}
        </span>
      </div>

      {/* Type tag below */}
      <span style={{
        position: "absolute", bottom: -16, left: "50%",
        transform: "translateX(-50%)", fontSize: 7, fontWeight: 700,
        color, letterSpacing: "0.06em", textTransform: "uppercase",
        whiteSpace: "nowrap", pointerEvents: "none",
        opacity: dimmed ? 0.3 : 0.7,
      }}>
        {raw.type}
      </span>

      {/* Connection handles (invisible) */}
      <Handle type="target" position={Position.Top}
        style={{ opacity: 0, top: r, left: r, width: 1, height: 1 }} />
      <Handle type="source" position={Position.Bottom}
        style={{ opacity: 0, top: r, left: r, width: 1, height: 1 }} />
    </div>
  );
}

const nodeTypes: NodeTypes = { round: RoundNode };

/* ════════════════════════════════════════════════════════════════════════════
   FORCE LAYOUT
   ════════════════════════════════════════════════════════════════════════════ */
interface ForceDatum extends SimulationNodeDatum { id: string; }

function computeForceLayout(
  rawNodes: NodeOut[], rawEdges: EdgeOut[],
): Record<string, { x: number; y: number }> {
  const ids = new Set(rawNodes.map(n => n.id));
  const validEdges = rawEdges.filter(e => ids.has(e.source_id) && ids.has(e.target_id));

  const spread = Math.sqrt(rawNodes.length) * 90;
  const datums: ForceDatum[] = rawNodes.map((n, i) => {
    const angle = (i / rawNodes.length) * 2 * Math.PI;
    return { id: n.id, x: Math.cos(angle) * spread, y: Math.sin(angle) * spread };
  });

  const links: SimulationLinkDatum<ForceDatum>[] = validEdges.map(e => ({
    source: e.source_id, target: e.target_id,
  }));

  forceSimulation<ForceDatum>(datums)
    .force("link", forceLink<ForceDatum, SimulationLinkDatum<ForceDatum>>(links)
      .id(d => d.id).distance(160).strength(0.35))
    .force("charge", forceManyBody().strength(-520))
    .force("center", forceCenter(0, 0))
    .force("collide", forceCollide<ForceDatum>(d => (NODE_SIZE[(rawNodes.find(n => n.id === d.id)?.type) ?? ""] ?? 28) + 20))
    .force("x", forceX(0).strength(0.04))
    .force("y", forceY(0).strength(0.04))
    .stop()
    .tick(350);

  const pos: Record<string, { x: number; y: number }> = {};
  datums.forEach(d => { pos[d.id] = { x: d.x ?? 0, y: d.y ?? 0 }; });
  return pos;
}

/* ════════════════════════════════════════════════════════════════════════════
   DETAIL TOOLTIP (appears next to the focused node)
   ════════════════════════════════════════════════════════════════════════════ */
const DetailTooltip: React.FC<{ node: NodeOut; color: string; onClose: () => void }> = ({ node, color, onClose }) => (
  <div style={{
    position: "absolute", top: 16, left: 16, zIndex: 50, width: 320,
    background: "var(--bg)", border: `1px solid ${color}55`,
    borderRadius: 14, overflow: "hidden",
    boxShadow: `0 8px 40px rgba(0,0,0,0.3), 0 0 20px ${color}22`,
    animation: "tooltip-in 0.25s ease-out",
  }}>
    {/* Header */}
    <div style={{
      padding: "12px 16px", background: `${color}15`,
      borderBottom: `1px solid ${color}33`,
      display: "flex", alignItems: "center", gap: 10,
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: "50%",
        background: `${color}33`, border: `2px solid ${color}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 10, fontWeight: 800, color,
      }}>
        {node.type.charAt(0)}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {node.name}
        </div>
        <div style={{ fontSize: 10, color, fontWeight: 600,
          textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {node.type}
        </div>
      </div>
      <button onClick={onClose} style={{
        background: "none", border: "none", color: "var(--text-muted)",
        fontSize: 18, cursor: "pointer", lineHeight: 1, padding: 4,
      }}>×</button>
    </div>

    {/* Body */}
    <div style={{ padding: "12px 16px", fontSize: 11, lineHeight: 1.7 }}>
      {node.signature && (
        <div style={{
          padding: "6px 10px", borderRadius: 6, marginBottom: 10,
          background: "var(--surface)", fontFamily: "var(--font-mono)",
          fontSize: 10, borderLeft: `3px solid ${color}`, color: "var(--text)",
          overflowX: "auto", whiteSpace: "pre-wrap",
        }}>
          {node.signature}
        </div>
      )}
      {node.docstring && (
        <div style={{
          padding: "6px 10px", borderRadius: 6, marginBottom: 10,
          background: "var(--surface)", fontStyle: "italic",
          color: "var(--text-muted)", fontSize: 11,
        }}>
          {node.docstring}
        </div>
      )}
      <Detail label="File" value={node.file_path} />
      {node.start_line != null && (
        <Detail label="Lines" value={`${node.start_line} – ${node.end_line}`} />
      )}
      {node.qualified_name && <Detail label="Qualified" value={node.qualified_name} />}
      {node.language && <Detail label="Language" value={node.language} />}
    </div>
  </div>
);

const Detail: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div style={{ marginBottom: 6 }}>
    <span style={{ color: "var(--text-muted)", fontSize: 9, textTransform: "uppercase",
      letterSpacing: "0.06em" }}>{label}: </span>
    <span style={{ color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: 10,
      wordBreak: "break-all" }}>{value}</span>
  </div>
);

/* ════════════════════════════════════════════════════════════════════════════
   MAIN COMPONENT (inner, needs ReactFlowProvider)
   ════════════════════════════════════════════════════════════════════════════ */
interface InnerProps extends Props {}

const GraphViewInner: React.FC<InnerProps> = ({ nodes: rawNodes, edges: rawEdges, onNodeClick }) => {
  const { fitView, setCenter } = useReactFlow();
  const [rfNodes, setRfNodes] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges] = useEdgesState<Edge>([]);
  const prevKeyRef = useRef("");
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const positionsRef = useRef<Record<string, { x: number; y: number }>>({});
  const [enabledEdges, setEnabledEdges] = useState<Set<string>>(
    new Set(EDGE_TYPES)
  );
  const [showFilters, setShowFilters] = useState(false);

  // Ego-graph mode: hide everything outside N hops of the focused node.
  const [egoMode, setEgoMode] = useState(false);
  const [egoHops, setEgoHops] = useState<1 | 2>(1);

  /** BFS up to `hops` edges from `rootId`; returns reachable node ids (inclusive). */
  function egoNeighborhood(
    rootId: string, edges: EdgeOut[], hops: number,
  ): Set<string> {
    const visible = new Set<string>([rootId]);
    let frontier: Set<string> = new Set([rootId]);
    for (let h = 0; h < hops; h++) {
      const next: Set<string> = new Set();
      for (const e of edges) {
        if (frontier.has(e.source_id) && !visible.has(e.target_id)) {
          next.add(e.target_id); visible.add(e.target_id);
        }
        if (frontier.has(e.target_id) && !visible.has(e.source_id)) {
          next.add(e.source_id); visible.add(e.source_id);
        }
      }
      if (next.size === 0) break;
      frontier = next;
    }
    return visible;
  }

  const toggleEdgeType = (t: string) => {
    setEnabledEdges(prev => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  };

  // Filter edges based on enabled types
  const filteredEdges = rawEdges.filter(e => enabledEdges.has(e.type));

  // Build graph whenever source data changes
  useEffect(() => {
    if (rawNodes.length === 0) { setRfNodes([]); setRfEdges([]); return; }
    const key = rawNodes.map(n => n.id).sort().join(",");
    if (key === prevKeyRef.current) return;
    prevKeyRef.current = key;

    const positions = computeForceLayout(rawNodes, rawEdges);
    positionsRef.current = positions;
    applyGraph(rawNodes, filteredEdges, positions, null);
  }, [rawNodes, rawEdges]);

  // Re-apply when focus, edge filters, or ego-mode settings change
  useEffect(() => {
    if (rawNodes.length > 0) {
      applyGraph(rawNodes, filteredEdges, positionsRef.current, focusedId);
    }
  }, [focusedId, enabledEdges, egoMode, egoHops]);

  function applyGraph(
    rn: NodeOut[], re: EdgeOut[],
    positions: Record<string, { x: number; y: number }>,
    focus: string | null,
  ) {
    // Find neighbors of focused node
    const neighborIds = new Set<string>();
    if (focus) {
      neighborIds.add(focus);
      re.forEach(e => {
        if (e.source_id === focus) neighborIds.add(e.target_id);
        if (e.target_id === focus) neighborIds.add(e.source_id);
      });
    }

    // Ego-graph: if enabled + a node is focused, restrict the visible set to
    // the N-hop neighborhood. Outside that set, nodes and edges are hidden.
    const egoVisible =
      egoMode && focus ? egoNeighborhood(focus, re, egoHops) : null;

    const visibleRn = egoVisible ? rn.filter(n => egoVisible.has(n.id)) : rn;

    const nodes: Node[] = visibleRn.map(n => ({
      id: n.id,
      type: "round",
      position: positions[n.id] ?? { x: 0, y: 0 },
      data: {
        label: n.name, raw: n,
        focused: focus === n.id,
        // In ego mode everything shown is a neighbor, so no dimming.
        dimmed: !egoVisible && !!focus && !neighborIds.has(n.id),
      },
      style: { width: (NODE_SIZE[n.type] ?? 28) * 2, height: (NODE_SIZE[n.type] ?? 28) * 2 },
    }));

    const edges: Edge[] = re
      .filter(e =>
        (!egoVisible || (egoVisible.has(e.source_id) && egoVisible.has(e.target_id)))
        && positions[e.source_id] && positions[e.target_id]
      )
      .map(e => {
        const connected = focus
          ? (e.source_id === focus || e.target_id === focus)
          : false;
        const edgeColor = EDGE_COLORS[e.type] ?? "#888780";
        return {
          id: e.id,
          source: e.source_id,
          target: e.target_id,
          type: "default",
          style: {
            stroke: connected ? edgeColor : edgeColor,
            strokeWidth: connected ? 2.5 : 1,
            strokeOpacity: focus ? (connected ? 0.9 : 0.08) : 0.35,
            transition: "stroke-opacity 0.35s, stroke-width 0.35s",
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: edgeColor,
            width: connected ? 10 : 6,
            height: connected ? 10 : 6,
          },
          animated: connected,
        };
      });

    setRfNodes(nodes);
    setRfEdges(edges);
  }

  // Click handler — toggle zoom
  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const raw = (node.data as any).raw as NodeOut;
    const id = node.id;

    if (focusedId === id) {
      // Already focused → zoom back out
      setFocusedId(null);
      onNodeClick(raw);  // also inform parent
      setTimeout(() => fitView({ padding: 0.15, duration: 600 }), 50);
    } else {
      // Focus on this node — zoom in
      setFocusedId(id);
      onNodeClick(raw);
      const pos = positionsRef.current[id];
      if (pos) {
        const r = NODE_SIZE[raw.type] ?? 28;
        setCenter(pos.x + r, pos.y + r, { zoom: 2.2, duration: 600 });
      }
    }
  }, [focusedId, onNodeClick, fitView, setCenter]);

  // Click on pane → deselect
  const handlePaneClick = useCallback(() => {
    if (focusedId) {
      setFocusedId(null);
      setTimeout(() => fitView({ padding: 0.15, duration: 500 }), 50);
    }
  }, [focusedId, fitView]);

  // ── Empty state ──────────────────────────────────────────────────────────
  if (rawNodes.length === 0) {
    return (
      <div style={{
        flex: 1, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
        color: "var(--text-muted)", gap: 14,
      }}>
        <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
          {[[40,10],[70,28],[70,56],[40,74],[10,56],[10,28]].map(([cx,cy],i,a)=>(
            <React.Fragment key={i}>
              <line x1={cx} y1={cy} x2={a[(i+1)%a.length][0]} y2={a[(i+1)%a.length][1]}
                stroke="var(--border)" strokeWidth="1" opacity="0.5" />
              {i%2===0 && <line x1={cx} y1={cy} x2={a[(i+3)%a.length][0]} y2={a[(i+3)%a.length][1]}
                stroke="var(--border)" strokeWidth="0.5" opacity="0.3" />}
              <circle cx={cx} cy={cy} r={5+i%3} fill="none"
                stroke="var(--text-muted)" strokeWidth="1.5" opacity="0.5" />
            </React.Fragment>
          ))}
        </svg>
        <span style={{ fontSize: 14 }}>Index a repository to see the knowledge graph</span>
        <span style={{ fontSize: 11, opacity: 0.5 }}>Enter a path above and click Index</span>
      </div>
    );
  }

  if (rfNodes.length === 0 && rawNodes.length > 0) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center",
        justifyContent: "center", color: "var(--text-muted)", fontSize: 13 }}>
        ◈ Computing graph layout…
      </div>
    );
  }

  const focusedNode = focusedId ? rawNodes.find(n => n.id === focusedId) ?? null : null;

  return (
    <div style={{ flex: 1, position: "relative" }}>
      {/* CSS keyframes */}
      <style>{`
        @keyframes pulse-ring {
          0% { transform: scale(1); opacity: 0.6; }
          70% { transform: scale(1.4); opacity: 0; }
          100% { transform: scale(1.4); opacity: 0; }
        }
        @keyframes tooltip-in {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={() => {}}
        onEdgesChange={() => {}}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15, duration: 400 }}
        minZoom={0.04}
        maxZoom={5}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        defaultEdgeOptions={{ type: "default" }}
      >
        <Background color="var(--border)" gap={36} size={0.6} />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={n => {
            const t = (n.data as any)?.raw?.type;
            return NODE_COLORS[t] ?? "#888780";
          }}
          nodeStrokeWidth={0}
          maskColor="var(--bg)cc"
          style={{ borderRadius: 10, border: "1px solid var(--border)" }}
        />
      </ReactFlow>

      {/* Detail tooltip */}
      {focusedNode && (
        <DetailTooltip
          node={focusedNode}
          color={NODE_COLORS[focusedNode.type] ?? "#888780"}
          onClose={() => {
            setFocusedId(null);
            setTimeout(() => fitView({ padding: 0.15, duration: 500 }), 50);
          }}
        />
      )}

      {/* Legend + Edge Filters */}
      <div style={{
        position: "absolute", top: 12, right: 12, zIndex: 10,
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, padding: "10px 14px", fontSize: 10,
        display: "flex", flexDirection: "column", gap: 5,
        boxShadow: "0 4px 20px rgba(0,0,0,0.1)",
      }}>
        {/* Node count badge */}
        <div style={{ display: "flex", gap: 8, justifyContent: "center",
          padding: "2px 0 4px", borderBottom: "1px solid var(--border)",
          marginBottom: 2, pointerEvents: "none" }}>
          <span style={{ color: "var(--text-muted)", fontSize: 9 }}>
            {rawNodes.length} nodes · {filteredEdges.length} edges
          </span>
        </div>

        <span style={{ color: "var(--text-muted)", fontSize: 8,
          textTransform: "uppercase", letterSpacing: "0.1em",
          fontWeight: 800, pointerEvents: "none" }}>Nodes</span>
        {TYPE_ORDER.map(t => (
          <div key={t} style={{ display: "flex", alignItems: "center", gap: 6, pointerEvents: "none" }}>
            <div style={{
              width: 12, height: 12, borderRadius: "50%",
              background: (NODE_COLORS[t] ?? "#888") + "44",
              border: `2px solid ${NODE_COLORS[t] ?? "#888"}`,
              boxShadow: `0 0 4px ${NODE_COLORS[t] ?? "#888"}44`,
            }} />
            <span style={{ color: "var(--text)", fontSize: 9 }}>{t}</span>
          </div>
        ))}

        {/* Ego-graph toggle */}
        <div style={{ borderTop: "1px solid var(--border)", marginTop: 4, paddingTop: 6 }}>
          <div style={{ display: "flex", alignItems: "center",
              justifyContent: "space-between", gap: 8 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 5,
                cursor: "pointer", fontSize: 9, fontWeight: 800,
                textTransform: "uppercase", letterSpacing: "0.1em",
                color: egoMode ? "var(--text)" : "var(--text-muted)" }}>
              <input
                type="checkbox"
                checked={egoMode}
                onChange={e => setEgoMode(e.target.checked)}
                style={{ width: 11, height: 11 }}
              />
              Ego Graph
            </label>
            <div style={{ display: "flex", gap: 2, opacity: egoMode ? 1 : 0.4 }}>
              {[1, 2].map(h => (
                <button
                  key={h}
                  disabled={!egoMode}
                  onClick={() => setEgoHops(h as 1 | 2)}
                  style={{
                    padding: "1px 6px", fontSize: 9, fontWeight: 700,
                    border: `1px solid var(--border)`,
                    borderRadius: 4,
                    background: egoHops === h ? "var(--text)" : "transparent",
                    color: egoHops === h ? "var(--bg)" : "var(--text-muted)",
                    cursor: egoMode ? "pointer" : "default",
                  }}
                >
                  {h}-hop
                </button>
              ))}
            </div>
          </div>
          {egoMode && !focusedId && (
            <div style={{ fontSize: 8, color: "var(--text-muted)",
                marginTop: 3, fontStyle: "italic" }}>
              Click a node to isolate its neighborhood
            </div>
          )}
        </div>

        {/* Edge type filter toggle */}
        <div style={{ borderTop: "1px solid var(--border)", marginTop: 4, paddingTop: 6 }}>
          <div
            style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer",
              color: "var(--text-muted)", fontSize: 8, textTransform: "uppercase",
              letterSpacing: "0.1em", fontWeight: 800 }}
            onClick={() => setShowFilters(!showFilters)}
          >
            <span>{showFilters ? "▾" : "▸"}</span>
            <span>Edge Filters</span>
          </div>
          {showFilters && (
            <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 4 }}>
              {EDGE_TYPES.map(t => (
                <label key={t} style={{ display: "flex", alignItems: "center", gap: 5,
                  cursor: "pointer", fontSize: 9, color: enabledEdges.has(t) ? "var(--text)" : "var(--text-muted)" }}>
                  <input
                    type="checkbox"
                    checked={enabledEdges.has(t)}
                    onChange={() => toggleEdgeType(t)}
                    style={{ width: 11, height: 11, accentColor: EDGE_COLORS[t] ?? "#888" }}
                  />
                  <div style={{
                    width: 16, height: 2, borderRadius: 1,
                    background: enabledEdges.has(t) ? (EDGE_COLORS[t] ?? "#888") : "var(--border)",
                  }} />
                  {t}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Hint */}
      {!focusedId && (
        <div style={{
          position: "absolute", bottom: 14, left: "50%",
          transform: "translateX(-50%)", zIndex: 10,
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 8, padding: "6px 14px", fontSize: 10,
          color: "var(--text-muted)", pointerEvents: "none",
          boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
        }}>
          Click a node to zoom in · Click again to zoom out
        </div>
      )}
    </div>
  );
};

/* ════════════════════════════════════════════════════════════════════════════
   EXPORTED WRAPPER (provides ReactFlowProvider)
   ════════════════════════════════════════════════════════════════════════════ */
interface Props {
  nodes: NodeOut[];
  edges: EdgeOut[];
  onNodeClick: (node: NodeOut) => void;
}

export const GraphView: React.FC<Props> = (props) => (
  <ReactFlowProvider>
    <GraphViewInner {...props} />
  </ReactFlowProvider>
);
