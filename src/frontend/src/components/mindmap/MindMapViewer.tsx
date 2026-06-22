'use client';

import { useCallback, useEffect, useState, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  NodeMouseHandler,
  BackgroundVariant,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { BookOpen } from 'lucide-react';
import RootNode from './nodes/RootNode';
import BranchNode from './nodes/BranchNode';
import CitationPanel from './CitationPanel';
import { MindMapData, Citation } from '@/lib/mindmap/types';
import { layoutTreeMindMap, convertMindMapToFlow } from '@/lib/mindmap/convertToFlow';

interface MindMapViewerProps {
  data: MindMapData;
}

const nodeTypes = {
  rootNode: RootNode,
  branchNode: BranchNode,
};

function MindMapViewer({ data }: MindMapViewerProps) {
  const [selectedNode, setSelectedNode] = useState<{
    id: string;
    label: string;
    citations: Citation[];
  } | null>(null);

  const initialFlow = useMemo(() => {
    // Use radial layout for better mindmap visualization
    const { nodes, edges } = layoutTreeMindMap(data);
    return { nodes, edges };
  }, [data]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialFlow.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialFlow.edges);

  useEffect(() => {
    const flow = layoutTreeMindMap(data);
    setNodes(flow.nodes);
    setEdges(flow.edges);
  }, [data, setNodes, setEdges]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (event, node) => {
      const citations = node.data.citations || [];
      setSelectedNode({
        id: node.id,
        label: node.data.label,
        citations,
      });
    },
    [],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const onToggleNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === nodeId) {
            const hasChildren =
              node.data.hasChildren !== undefined ? node.data.hasChildren : false;
            return {
              ...node,
              data: {
                ...node.data,
                isExpanded: !node.data.isExpanded,
              },
            };
          }
          return node;
        }),
      );
    },
    [setNodes],
  );

  // Update node data with toggle handler
  useEffect(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: {
          ...node.data,
          onToggle: () => onToggleNode(node.id),
        },
      })),
    );
  }, [onToggleNode, setNodes]);

  return (
    <div className="w-full h-[calc(100vh-200px)] min-h-[600px] bg-gray-50 rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      <div className="flex h-full">
        <div className="flex-1 relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.1}
            maxZoom={2}
            defaultEdgeOptions={{
              type: 'smoothstep',
              style: { strokeWidth: 2 },
            }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e2e8f0" />
            <Controls className="bg-white border border-gray-200 shadow-md rounded-lg" />
            <MiniMap
              className="bg-white border border-gray-200 shadow-md"
              nodeColor={(node) => {
                if (node.type === 'rootNode') return '#3b82f6';
                return '#10b981';
              }}
              maskColor="rgba(0, 0, 0, 0.1)"
            />
          </ReactFlow>

          <div className="absolute top-4 left-4 bg-white/90 backdrop-blur-sm px-3 py-2 rounded-lg border border-gray-200 shadow-sm">
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <BookOpen className="w-4 h-4 text-blue-500" />
              <span className="font-medium">Mind Map Preview</span>
            </div>
          </div>
        </div>

        {selectedNode && (
          <div className="w-80 border-l border-gray-200 bg-gray-50/50 p-4 overflow-y-auto">
            <CitationPanel
              citations={selectedNode.citations}
              nodeLabel={selectedNode.label}
              onClose={() => setSelectedNode(null)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default MindMapViewer;