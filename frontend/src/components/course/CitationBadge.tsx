"use client"

import { BookOpen, AlertTriangle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { Citation } from "@/types/course"

interface CitationBadgeProps {
  citations?: Citation[]
}

export function CitationBadge({ citations }: CitationBadgeProps) {
  // Quality Gate 2 compliance: warn if citations are missing
  if (!citations || citations.length === 0) {
    return (
      <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Không có trích dẫn
      </Badge>
    )
  }

  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {citations.map((citation, index) => (
        <TooltipProvider key={`${citation.chunk_id}-${index}`}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge
                variant="secondary"
                className="bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100 cursor-help text-xs"
              >
                <BookOpen className="h-3 w-3 mr-1" />
                Trang {citation.page} - {citation.source}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              <p className="text-xs">
                chunk_id: <code className="font-mono">{citation.chunk_id}</code>
              </p>
              <p className="text-xs text-muted-foreground">
                Click để trace ngược về tài liệu gốc
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ))}
    </div>
  )
}