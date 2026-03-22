"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import Dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";

import { useDashboardStore } from "@/store/dashboard";
import type { CallTreeData } from "@/types/events";

/* ── types ───────────────────────────────────────────────────────────── */

type NodeState = "idle" | "active" | "visited";

interface IvrNodeData extends Record<string, unknown> {
  label: string;
  state: NodeState;
  inputType: string;
}

/* ── custom node ─────────────────────────────────────────────────────── */

function IvrNodeComponent({ data }: { data: IvrNodeData }) {
  const isActive = data.state === "active";
  const isVisited = data.state === "visited";

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-transparent !border-0 !w-0 !h-0"
      />
      <div
        className={[
          "relative px-5 py-3 rounded-xl text-xs font-semibold text-center min-w-[130px]",
          "transition-all duration-500 ease-out border-2",
          isActive
            ? "bg-blue-600 border-blue-400 text-white scale-110 z-10 animate-glow-pulse"
            : isVisited
              ? "bg-emerald-950/50 border-emerald-500/50 text-emerald-300"
              : "bg-zinc-800/70 border-zinc-700/40 text-zinc-400",
        ].join(" ")}
      >
        {isActive && (
          <span className="absolute inset-0 rounded-xl bg-blue-400/10 animate-pulse pointer-events-none" />
        )}
        <span className="relative z-10">{data.label}</span>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-transparent !border-0 !w-0 !h-0"
      />
    </>
  );
}

const nodeTypes = { ivrNode: IvrNodeComponent };

/* ── dagre layout ────────────────────────────────────────────────────── */

function buildLayout(
  tree: CallTreeData,
  currentNodeId: string | null,
  visitedNodeIds: string[],
): { nodes: Node<IvrNodeData>[]; edges: Edge[] } {
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: "TB",
    nodesep: 60,
    ranksep: 80,
    marginx: 40,
    marginy: 40,
  });

  for (const node of tree.nodes) {
    g.setNode(node.id, { width: 160, height: 48 });
  }
  for (const node of tree.nodes) {
    for (const t of node.transitions) {
      g.setEdge(node.id, t.next_node_id);
    }
  }
  Dagre.layout(g);

  const visited = new Set(visitedNodeIds);

  const nodes: Node<IvrNodeData>[] = tree.nodes.map((n) => {
    const pos = g.node(n.id);
    const state: NodeState =
      n.id === currentNodeId
        ? "active"
        : visited.has(n.id)
          ? "visited"
          : "idle";
    return {
      id: n.id,
      type: "ivrNode",
      position: { x: pos.x - 80, y: pos.y - 24 },
      data: { label: n.label, state, inputType: n.input_type },
    };
  });

  const edges: Edge[] = tree.nodes.flatMap((n) =>
    n.transitions.map((t) => {
      const srcHit = visited.has(n.id) || n.id === currentNodeId;
      const tgtHit = visited.has(t.next_node_id) || t.next_node_id === currentNodeId;
      const traversed = srcHit && tgtHit;

      return {
        id: `e-${n.id}-${t.next_node_id}`,
        source: n.id,
        target: t.next_node_id,
        label: t.label || t.input,
        animated: traversed,
        style: {
          stroke: traversed ? "#10b981" : "#27272a",
          strokeWidth: traversed ? 2.5 : 1,
        },
        labelStyle: {
          fill: traversed ? "#6ee7b7" : "#52525b",
          fontSize: 10,
          fontWeight: traversed ? 600 : 400,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: traversed ? "#10b981" : "#3f3f46",
          width: 14,
          height: 14,
        },
      };
    }),
  );

  return { nodes, edges };
}

/* ── component ───────────────────────────────────────────────────────── */

export default function CallTreeGraph() {
  const callTree = useDashboardStore((s) => s.callTree);
  const currentNodeId = useDashboardStore(
    (s) => (s.activeSessionId ? s.sessions[s.activeSessionId]?.currentNodeId : null) ?? null,
  );
  const visitedNodeIds = useDashboardStore(
    (s) => s.activeSessionId ? s.sessions[s.activeSessionId]?.visitedNodeIds ?? [] : [],
  );

  const { nodes, edges } = useMemo(() => {
    if (!callTree) return { nodes: [] as Node<IvrNodeData>[], edges: [] as Edge[] };
    return buildLayout(callTree, currentNodeId, visitedNodeIds);
  }, [callTree, currentNodeId, visitedNodeIds]);

  if (!callTree) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        <div className="flex flex-col items-center gap-2">
          <div className="w-6 h-6 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" />
          <span>Loading call tree&hellip;</span>
        </div>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      minZoom={0.3}
      maxZoom={1.8}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      className="!bg-transparent"
    >
      <Background gap={24} size={1} color="#18181b" />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
