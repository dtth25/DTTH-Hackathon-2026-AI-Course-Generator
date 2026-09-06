import React from "react";
import { AlertTriangle, CheckCircle2, CircleHelp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DocumentQualityReport } from "@/lib/types";

interface QualityScoreBadgeProps {
  score?: number;
  report?: DocumentQualityReport | null;
  className?: string;
}

export function QualityScoreBadge({
  score,
  report,
  className,
}: QualityScoreBadgeProps) {
  const baseClass = "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold shadow-[var(--shadow-xs)]";

  if (report?.extraction_complete === true) {
    return (
      <span className={cn(baseClass, "border-success/20 bg-success/10 text-success", className)}
        title="Trạng thái trích xuất nguồn; độ trung thực của nội dung chưa được đánh giá">
        <CheckCircle2 className="h-3.5 w-3.5" />
        <span>Trích xuất hoàn tất{report.indexed_chunk_count !== undefined ? ` • ${report.indexed_chunk_count} đoạn nguồn` : ""} • Độ trung thực: chưa đánh giá</span>
      </span>
    );
  }

  if (report?.extraction_complete === false) {
    return (
      <span className={cn(baseClass, "border-warning/20 bg-warning/10 text-warning", className)}>
        <AlertTriangle className="h-3.5 w-3.5" />
        <span>Trích xuất chưa hoàn tất • Độ trung thực: chưa đánh giá</span>
      </span>
    );
  }

  if (report?.structural_validity !== undefined) {
    return (
      <span className={cn(baseClass, "border-border bg-muted text-muted-foreground", className)}>
        <CircleHelp className="h-3.5 w-3.5" />
        <span>Kiểm tra cấu trúc • {report.structural_validity}/100</span>
      </span>
    );
  }

  if (score !== undefined && score > 0) {
    return (
      <span className={cn(baseClass, "border-border bg-muted text-muted-foreground", className)}
        title="Điểm tương thích cũ chỉ phản ánh kiểm tra cấu trúc hoặc độ phủ nguồn">
        <CircleHelp className="h-3.5 w-3.5" />
        <span>Kiểm tra cấu trúc (cũ) • {score}/100</span>
      </span>
    );
  }

  return (
    <span className={cn(baseClass, "border-border bg-muted text-muted-foreground", className)}>
      <CircleHelp className="h-3.5 w-3.5" />
      <span>Chưa đánh giá chất lượng</span>
    </span>
  );
}
