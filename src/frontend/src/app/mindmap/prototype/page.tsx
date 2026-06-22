'use client';

import { Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import MindMapViewer from '@/components/mindmap/MindMapViewer';
import { mockMindMapData } from '@/lib/mindmap/mockData';

function LoadingFallback() {
  return (
    <div className="w-full h-[calc(100vh-200px)] min-h-[600px] flex items-center justify-center bg-gray-50 rounded-xl border border-gray-200">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        <p className="text-sm text-gray-600">Loading Mind Map...</p>
      </div>
    </div>
  );
}

function MindMapPrototype() {
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Mind Map Prototype</h1>
        <p className="text-sm text-gray-600 mt-1">
          Interactive mind map visualization with citation support
        </p>
      </div>

      <Suspense fallback={<LoadingFallback />}>
        <MindMapViewer data={mockMindMapData} />
      </Suspense>

      <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <h2 className="text-sm font-semibold text-blue-900 mb-2">Prototype Features</h2>
        <ul className="text-xs text-blue-800 space-y-1 list-disc list-inside">
          <li>Click on nodes to view citations (page numbers & source files)</li>
          <li>Use mouse wheel to zoom in/out</li>
          <li>Drag canvas to pan around</li>
          <li>Click expand/collapse buttons on nodes to toggle children</li>
          <li>Use minimap in bottom-right for navigation</li>
        </ul>
      </div>
    </div>
  );
}

export default MindMapPrototype;