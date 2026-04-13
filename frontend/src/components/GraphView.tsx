import React, { useCallback, useMemo } from "react";
import {
  ReactFlow, Background, Controls, MiniMap,
  type Node, type Edge,
  useNodesState, useEdgesState,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { NodeOut, EdgeOut } from "../types/graph";
import { NODE_COLORS, EDGE_COLORS } from "../types/graph";

interface Props {
  nodes: NodeOut[];
  edges: EdgeOut[];
  onNodeClick: (node: NodeOut) => void;
}

const SPACING_X = 220;
const SPACING_Y = 100;

function layoutNodes(nodes: NodeOut[]): Record<string, { x: number; y: number }> {
  const typeOrder = ["FILE", "MODULE", "CLASS", "FUNCTION", "METHOD", "VARIABLE", "TYPE"];
  const byType: Record<string, NodeOut[]> = {};
  for (const n of nodes) {
    if (!byType[n.type]) byType[n.type] = [];
    byType[n.type].push(n);
  }
  const positions: Record<string, { x: number; y: number }> = {};
  let y = 0;
  for (const type of typeOrder) {
    const group = byType[type] ?? [];
    group.forEach((node, i) => {
      positions[node.id] = { x: i * SPACING_X, y };
    });
    if (group.length > 0) y += SPACING_Y;
  }
  return positions;
}

export const GraphView: React.FC<Props> = ({ nodes: rawNodes, edges: rawEdges, onNodeClick }) => {
  const positions = useMemo(() => layoutNodes(rawNodes), [rawNodes]);

  const rfNodes: Node[] = useMemo(() =>
    rawNodes.map((n) => ({
      id: n.id,
      position: positions[n.id] ?? { x: 0, y: 0 },
      data: { label: n.name, raw: n },
      style: {
        background: (NODE_COLORS[n.type] ?? "#888780") + "18",
        border: `1.5px solid ${NODE_COLORS[n.type] ?? "#888780"}`,
        borderRadius: 8, padding: "6px 12px",
        fontSize: 12, fontWeight: 500,
        color: "var(--text)", minWidth: 120, maxWidth: 200,
      },
    })),
  [rawNodes, positions]);

  const rfEdges: Edge[] = useMemo(() =>
    rawEdges.map((e) => ({
      id: e.id,
      source: e.source_id,
      target: e.target_id,
      label: e.type,
      labelStyle: { fontSize: 9, fill: "var(--text-muted)" },
      style: { stroke: EDGE_COLORS[e.type] ?? "#888780", strokeWidth: 1 },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: EDGE_COLORS[e.type] ?? "#888780", width: 12, height: 12,
      },
      animated: e.type === "CALLS",
    })),
  [rawEdges]);

  const [nodes, , onNodesChange] = useNodesState(rfNodes);
  const [edges, , onEdgesChange] = useEdgesState(rfEdges);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    onNodeClick((node.data as any).raw as NodeOut);
  }, [onNodeClick]);

  if (rawNodes.length === 0) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center",
        justifyContent: "center", color: "var(--text-muted)", fontSize: 13 }}>
        Index a repository to see the knowledge graph
      </div>
    );
  }

  return (
    <div style={{ flex: 1, position: "relative" }}>
      <ReactFlow
        nodes={nodes} edges={edges}
        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1} maxZoom={2}
      >
        <Background color="var(--border)" gap={24} />
        <Controls />
        <MiniMap
          nodeColor={(n) => NODE_COLORS[(n.data as any)?.raw?.type] ?? "#888780"}
          maskColor="var(--bg)cc"
        />
      </ReactFlow>
    </div>
  );
};
