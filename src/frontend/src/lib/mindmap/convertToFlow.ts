import { MindMapData, MindMapNode } from './types';
import { Node, Edge } from 'reactflow';

const NODE_WIDTH = 240;
const NODE_HEIGHT = 100;
const HORIZONTAL_SPACING = 80;
const VERTICAL_SPACING = 60;

export function convertMindMapToFlow(data: MindMapData): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let yPosition = 0;

  function traverseTree(
    node: MindMapNode,
    depth: number = 0,
    parentId?: string,
    siblingIndex: number = 0,
    siblingCount: number = 1,
  ) {
    const xPosition = depth * (NODE_WIDTH + HORIZONTAL_SPACING);
    const nodeId = node.id;

    const isRoot = depth === 0;
    const hasChildren = node.children && node.children.length > 0;

    nodes.push({
      id: nodeId,
      type: isRoot ? 'rootNode' : 'branchNode',
      position: { x: xPosition, y: yPosition },
      data: {
        label: node.label,
        citations: node.citations,
        isExpanded: true,
        hasChildren: !!hasChildren,
        depth,
        onToggle: () => {
          console.log('Toggle node:', nodeId);
        },
      },
    });

    if (parentId) {
      edges.push({
        id: `${parentId}-${nodeId}`,
        source: parentId,
        target: nodeId,
        type: 'smoothstep',
        animated: false,
        style: { stroke: '#cbd5e1', strokeWidth: 2 },
      });
    }

    if (hasChildren) {
      yPosition += NODE_HEIGHT + VERTICAL_SPACING;
      node.children!.forEach((child, index) => {
        traverseTree(child, depth + 1, nodeId, index, node.children!.length);
      });
    }
  }

  traverseTree(data.root, 0);

  return { nodes, edges };
}

export function layoutTreeMindMap(data: MindMapData): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const rootX = 400;
  const rootY = 300;

  function processNode(
    node: MindMapNode,
    depth: number = 0,
    parentId?: string,
    angleStart: number = -90,
    angleEnd: number = 90,
  ) {
    const isRoot = depth === 0;
    const hasChildren = node.children && node.children.length > 0;

    if (isRoot) {
      nodes.push({
        id: node.id,
        type: 'rootNode',
        position: { x: rootX - NODE_WIDTH / 2, y: rootY - NODE_HEIGHT / 2 },
        data: {
          label: node.label,
          citations: node.citations,
          isExpanded: true,
          hasChildren: !!hasChildren,
          depth,
          onToggle: () => {},
        },
      });
    } else {
      const radius = depth * (NODE_WIDTH + HORIZONTAL_SPACING);
      const midAngle = (angleStart + angleEnd) / 2;
      const angleRad = (midAngle * Math.PI) / 180;

      nodes.push({
        id: node.id,
        type: 'branchNode',
        position: {
          x: rootX + radius * Math.cos(angleRad) - NODE_WIDTH / 2,
          y: rootY + radius * Math.sin(angleRad) - NODE_HEIGHT / 2,
        },
        data: {
          label: node.label,
          citations: node.citations,
          isExpanded: true,
          hasChildren: !!hasChildren,
          depth,
          onToggle: () => {},
        },
      });
    }

    if (parentId) {
      edges.push({
        id: `${parentId}-${node.id}`,
        source: parentId,
        target: node.id,
        type: 'smoothstep',
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
      });
    }

    if (hasChildren) {
      const childCount = node.children!.length;
      const angleRange = angleEnd - angleStart;
      const angleStep = childCount > 1 ? angleRange / childCount : angleRange / 2;

      node.children!.forEach((child, index) => {
        const childAngleStart = angleStart + index * angleStep;
        const childAngleEnd = childAngleStart + angleStep;
        processNode(child, depth + 1, node.id, childAngleStart, childAngleEnd);
      });
    }
  }

  processNode(data.root);

  return { nodes, edges };
}

export function flattenMindMap(node: MindMapNode, depth: number = 0): Array<MindMapNode & { depth: number }> {
  const result: Array<MindMapNode & { depth: number }> = [{ ...node, depth }];

  if (node.children && node.children.length > 0) {
    node.children.forEach((child) => {
      result.push(...flattenMindMap(child, depth + 1));
    });
  }

  return result;
}

export function getNodeDepth(nodes: Node[], nodeId: string): number {
  const node = nodes.find((n) => n.id === nodeId);
  return node?.data?.depth ?? 0;
}

export function countNodes(data: MindMapData): number {
  return flattenMindMap(data.root).length;
}

export function getMaxDepth(data: MindMapData): number {
  let maxDepth = 0;

  function traverse(node: MindMapNode, depth: number) {
    if (depth > maxDepth) maxDepth = depth;
    node.children?.forEach((child) => traverse(child, depth + 1));
  }

  traverse(data.root, 0);
  return maxDepth;
}