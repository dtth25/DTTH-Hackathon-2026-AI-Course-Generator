'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { BookOpen, ChevronDown, ChevronUp } from 'lucide-react';
import { Citation } from '@/lib/mindmap/types';

interface RootNodeData {
  label: string;
  citations?: Citation[];
  isExpanded?: boolean;
  onToggle?: () => void;
}

function RootNode({ data, selected }: NodeProps<RootNodeData>) {
  const { label, citations, isExpanded = true, onToggle } = data;

  return (
    <div
      className={`
        relative px-6 py-4 rounded-xl border-2 shadow-lg min-w-[220px] max-w-[300px]
        ${selected ? 'border-blue-600 ring-2 ring-blue-200' : 'border-blue-400'}
        bg-gradient-to-br from-blue-500 to-blue-600 text-white
      `}
    >
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-blue-300 !border-2 !border-white"
      />

      <div className="flex items-start gap-3">
        <div className="mt-1">
          <BookOpen className="w-5 h-5" />
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm leading-tight break-words">
            {label}
          </h3>

          {citations && citations.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {citations.slice(0, 2).map((citation, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-white/20 backdrop-blur-sm"
                  title={`${citation.source} - Page ${citation.page}`}
                >
                  📄 p.{citation.page}
                </span>
              ))}
              {citations.length > 2 && (
                <span className="text-xs opacity-75">
                  +{citations.length - 2} more
                </span>
              )}
            </div>
          )}
        </div>

        {onToggle && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            className="p-1 rounded-full hover:bg-white/20 transition-colors"
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}

export default memo(RootNode);