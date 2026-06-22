'use client';

import { memo } from 'react';
import { X, ExternalLink } from 'lucide-react';
import { Citation } from '@/lib/mindmap/types';

interface CitationPanelProps {
  citations: Citation[];
  nodeLabel: string;
  onClose: () => void;
}

function CitationPanel({ citations, nodeLabel, onClose }: CitationPanelProps) {
  if (!citations || citations.length === 0) {
    return (
      <div className="w-80 bg-white border border-gray-200 rounded-xl shadow-lg p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 text-sm">Citations</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-gray-100 transition-colors"
            aria-label="Close panel"
          >
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        <div className="text-sm text-gray-500 italic">
          No citations available for this node
        </div>
      </div>
    );
  }

  return (
    <div className="w-80 bg-white border border-gray-200 rounded-xl shadow-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-semibold text-gray-900 text-sm">Citations</h3>
          <p className="text-xs text-gray-500 mt-0.5 truncate max-w-[200px]">
            {nodeLabel}
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md hover:bg-gray-100 transition-colors"
          aria-label="Close panel"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      <div className="space-y-2.5">
        {citations.map((citation, idx) => (
          <div
            key={`${citation.chunk_id}-${idx}`}
            className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100 hover:border-blue-200 transition-colors"
          >
            <div className="flex-shrink-0 mt-0.5">
              <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-medium">
                p.{citation.page}
              </div>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 text-xs text-gray-700">
                <ExternalLink className="w-3 h-3 text-gray-400" />
                <span className="font-medium truncate">{citation.source}</span>
              </div>
              <div className="mt-1 text-[10px] text-gray-400 font-mono truncate">
                {citation.chunk_id}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-3 border-t border-gray-100">
        <p className="text-[10px] text-gray-400 leading-relaxed">
          These citations reference specific pages and chunks in the original
          document. Click on a citation to view more details.
        </p>
      </div>
    </div>
  );
}

export default memo(CitationPanel);