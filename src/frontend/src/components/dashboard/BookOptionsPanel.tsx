"use client";

import { BookOpen, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const BOOK_DETAIL_OPTIONS = ["Tóm tắt", "Tiêu chuẩn", "Chuyên sâu"];

interface BookOptionsValue {
  detailLevel: string;
  userPrompt: string;
}

interface BookOptionsPanelProps {
  value: BookOptionsValue;
  onChange: (value: BookOptionsValue) => void;
  onSubmit: () => void;
  busy: boolean;
  submitLabel: string;
  progress?: number;
  documentProcessing?: boolean;
}

export function BookOptionsPanel({
  value,
  onChange,
  onSubmit,
  busy,
  submitLabel,
  progress = 0,
  documentProcessing = false,
}: BookOptionsPanelProps) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!busy && !documentProcessing) onSubmit();
      }}
      className="w-full max-w-md space-y-5 rounded-2xl border bg-card/40 p-5 text-left shadow-[var(--shadow-xs)]"
    >
      <div className="space-y-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Mức độ chi tiết
        </span>
        <div className="grid grid-cols-1 gap-2">
          {BOOK_DETAIL_OPTIONS.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => onChange({ ...value, detailLevel: opt })}
              disabled={busy}
              className={cn(
                "rounded-lg border py-2 text-sm font-semibold transition-colors",
                value.detailLevel === opt
                  ? "border-primary bg-primary/10 text-primary shadow-[var(--shadow-xs)]"
                  : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Yêu cầu bổ sung (tuỳ chọn)
        </span>
        <textarea
          value={value.userPrompt}
          onChange={(event) => onChange({ ...value, userPrompt: event.target.value })}
          disabled={busy}
          placeholder="Ví dụ: tập trung vào chương 2-4, thêm nhiều ví dụ thực tế…"
          rows={3}
          className="w-full resize-none rounded-lg border border-border/60 bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none"
        />
      </div>

      {busy ? (
        <div className="space-y-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <Button disabled size="lg" className="w-full gap-2 font-semibold">
            <RefreshCw className="h-5 w-5 animate-spin" /> Đang biên soạn sách ({progress}%)…
          </Button>
        </div>
      ) : documentProcessing ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border/60 py-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Tài liệu đang được xử lý, vui lòng đợi...
        </div>
      ) : (
        <Button type="submit" size="lg" className="w-full gap-2 font-semibold">
          <BookOpen className="h-5 w-5" />
          {submitLabel}
        </Button>
      )}
    </form>
  );
}
