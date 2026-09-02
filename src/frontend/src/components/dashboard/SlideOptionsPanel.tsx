"use client";

import { Loader2, Presentation, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SLIDE_MODES = [
  { value: "summary", label: "Tóm tắt", hint: "8 slide" },
  { value: "lesson", label: "Bài giảng", hint: "15 slide" },
  { value: "deep_dive", label: "Chuyên sâu", hint: "22 slide" },
] as const;

interface SlideOptionsValue {
  mode: "summary" | "lesson" | "deep_dive";
  focusPrompt: string;
}

interface SlideOptionsPanelProps {
  value: SlideOptionsValue;
  onChange: (value: SlideOptionsValue) => void;
  onSubmit: () => void;
  busy: boolean;
  submitLabel: string;
  progress?: number;
  documentProcessing?: boolean;
}

export function SlideOptionsPanel({
  value,
  onChange,
  onSubmit,
  busy,
  submitLabel,
  progress = 0,
  documentProcessing = false,
}: SlideOptionsPanelProps) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!busy && !documentProcessing) onSubmit();
      }}
      className="w-full max-w-md space-y-5 rounded-xl border bg-card/40 p-5 text-left shadow-[var(--shadow-xs)]"
    >
      <div className="space-y-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Độ sâu bài giảng</span>
        <div className="grid grid-cols-3 gap-2">
          {SLIDE_MODES.map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={busy}
              onClick={() => onChange({ ...value, mode: option.value })}
              className={cn(
                "rounded-lg border px-2 py-2 text-xs font-semibold transition-colors",
                value.mode === option.value
                  ? "border-primary bg-primary/10 text-primary shadow-[var(--shadow-xs)]"
                  : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              <span className="block">{option.label}</span>
              <span className="block text-[10px] font-normal opacity-80">{option.hint}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <label htmlFor="slide-focus" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Trọng tâm mong muốn (tùy chọn)</label>
        <textarea
          id="slide-focus"
          value={value.focusPrompt}
          onChange={(event) => onChange({ ...value, focusPrompt: event.target.value })}
          disabled={busy}
          rows={2}
          placeholder="Ví dụ: dành nhiều slide cho ví dụ và ứng dụng thực tế..."
          className="w-full resize-none rounded-lg border border-border/60 bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none"
        />
      </div>
      {busy ? (
        <>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <Button disabled size="lg" className="w-full gap-2 font-semibold">
            <RefreshCw className="h-5 w-5 animate-spin" /> Đang tạo slide ({progress}%)…
          </Button>
        </>
      ) : documentProcessing ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border/60 px-4 py-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Tài liệu đang được xử lý, vui lòng đợi...
        </div>
      ) : (
        <Button type="submit" size="lg" className="gap-2 font-semibold">
          <Presentation className="h-5 w-5" /> {submitLabel}
        </Button>
      )}
    </form>
  );
}
