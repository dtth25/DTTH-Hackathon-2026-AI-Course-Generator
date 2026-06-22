export interface Citation {
  page: number;
  source: string;
  chunk_id: string;
}

export interface MindMapNode {
  id: string;
  label: string;
  citations?: Citation[];
  children?: MindMapNode[];
}

export interface MindMapData {
  root: MindMapNode;
  branches: MindMapNode[];
}

export interface GenerateMindMapResponse {
  mindmap: MindMapData;
}