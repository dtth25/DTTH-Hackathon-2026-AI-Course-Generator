'use client';

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Lightbulb, ChevronDown, ChevronUp } from 'lucide-react';
import { Citation } from '@/lib/mindmap/types';

interface BranchNodeData {
  label: string;
  citations?: Citation[];
  isExpanded?: boolean;
  hasChildren?: boolean;
  onToggle?: () => void;
  depth?: number;
}

const depthColors = [
  { bg: 'bg-emerald-50', border: 'border-emerald-300', text: 'text-emerald-900' },
  { bg: 'bg-amber-50', border: 'border-amber-300', text: 'text-amber-900' },
  { bg: 'bg-purple-50', border: 'border-purple-300', text: 'text-purple-900' },
  { bg: 'bg-pink-50', border: 'border-pink-300', text: 'text-pink-900' },
];

function BranchNode({ data, selected }: NodeProps<BranchNodeData>) {
  const {
    label,
    citations,
    isExpanded = true,
    hasChildren = false,
    onToggle,
    depth = 0,
  } = data;

  const colorScheme = depthColors[Math.min(depth, depthColors.length - 1)];

  return (
    <div
      className={`
        relative px-4 py-3 rounded-lg border shadow-md min-w-[180px] max-w-[260px]
        ${selected ? `ring-2 ring-offset-2 ring-blue-300` : ''}
        ${colorScheme.bg} ${colorScheme.border} ${colorScheme.text}
      `}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-emerald-400 !border-2 !border-white"
      />

      {hasChildren && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="!bg-emerald-400 !border-2 !border-white"
        />
      )}

      <div className="flex items-start gap-2">
        <div className="mt-0.5">
          <Lightbulb className="w-4 h-4" />
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-xs leading-snug break-words">
            {label}
          </h4>

          {citations && citations.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {citations.slice(0, 1).map((citation, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] bg-black/5"
                  title={`${citation.source} - Page ${citation.page}`}
                >
                  📄 p.{citation.page}
                </span>
              ))}
              {citations.length > 1 && (
                <span className="text-[10px] opacity-60">
                  +{citations.length - 1}
                </span>
              )}
            </div>
          )}
        </div>

        {hasChildren && onToggle && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
            className="p-0.5 rounded hover:bg-black/5 transition-colors"
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}

export default memo(BranchNode);