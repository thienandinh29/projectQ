"use client";
import { useMemo } from "react";
import Image from "next/image";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type NodeProps,
  type Node,
  MarkerType,
} from "@xyflow/react";
import { Check, LockKeyhole } from "lucide-react";
import { layoutGraph, NODE_WIDTH, NODE_HEIGHT } from "@/lib/layout";
import type { KnowledgeGraph } from "@/lib/contracts";
import { vi } from "@/messages/vi";

type ConceptNode = Node<
  { label: string; mastery: number; mastered: boolean; active: boolean },
  "concept"
>;
function Concept({ data }: NodeProps<ConceptNode>) {
  return (
    <div
      className={`concept-node ${data.mastered ? "is-mastered" : data.active ? "is-active" : "is-pending"}`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="concept-node-top">
        <span className="node-dot">
          {data.mastered ? (
            <Check size={11} />
          ) : data.mastery < 0.2 ? (
            <LockKeyhole size={10} />
          ) : null}
        </span>
        <span>{Math.round(data.mastery * 100)}%</span>
      </div>
      <strong title={data.label}>{data.label}</strong>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { concept: Concept };
export function KnowledgeMap({
  graph,
  selected,
  onSelect,
}: {
  graph: KnowledgeGraph;
  selected: string;
  onSelect: (slug: string) => void;
}) {
  const nodes = useMemo<ConceptNode[]>(
    () =>
      layoutGraph(graph).map((node) => ({
        id: node.slug,
        type: "concept",
        position: node.position,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        selected: node.slug === selected,
        domAttributes: { "aria-roledescription": vi.graph.nodeDescription },
        data: {
          label: node.name_vi || node.slug,
          mastery: node.p_known,
          mastered: node.mastered,
          active: node.slug === selected,
        },
        ariaLabel: `${node.name_vi}, ${Math.round(node.p_known * 100)}%`,
      })),
    [graph, selected],
  );
  const edges = useMemo(
    () =>
      graph.edges.map((edge) => ({
        id: `${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        type: "smoothstep",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "#bec9b6",
          width: 14,
          height: 14,
        },
        style: { stroke: "#a5b395", strokeWidth: 1.5 },
        ariaLabel: `${vi.graph.edge}: ${edge.from} → ${edge.to}`,
        domAttributes: { "aria-roledescription": vi.graph.edgeDescription },
      })),
    [graph],
  );
  if (!graph.nodes.length)
    return (
      <div className="knowledge-map empty-map">
        <Image src="/sena.svg" alt="" width={85} height={85} />
        <h3>{vi.flow.emptyGraph}</h3>
        <p>{vi.flow.emptyGraphBody}</p>
      </div>
    );
  return (
    <div className="knowledge-map" role="region" aria-label={vi.mapLabel}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.13 }}
        minZoom={0.25}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        onNodeClick={(_, node) => onSelect(node.id)}
        onKeyDown={(event) => {
          if (
            (event.key === "Enter" || event.key === " ") &&
            event.target instanceof HTMLElement
          ) {
            const id = event.target
              .closest(".react-flow__node")
              ?.getAttribute("data-id");
            if (id) {
              event.preventDefault();
              onSelect(id);
            }
          }
        }}
        proOptions={{ hideAttribution: false }}
        ariaLabelConfig={{
          "controls.zoomIn.ariaLabel": vi.graph.zoomIn,
          "controls.zoomOut.ariaLabel": vi.graph.zoomOut,
          "controls.fitView.ariaLabel": vi.graph.fit,
          "controls.ariaLabel": vi.graph.controls,
          "node.a11yDescription.default": vi.graph.instructions,
          "node.a11yDescription.keyboardDisabled": vi.graph.instructions,
          "edge.a11yDescription.default": vi.graph.edgeInstructions,
          "node.a11yDescription.ariaLiveMessage": () => vi.graph.selected,
          "handle.ariaLabel": vi.graph.edge,
        }}
      >
        <Background color="#dfe4d8" gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
