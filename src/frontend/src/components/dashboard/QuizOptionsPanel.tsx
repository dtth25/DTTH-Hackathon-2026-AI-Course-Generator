"use client";

import { HelpCircle, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const QUANTITY_OPTIONS = [5, 10, 15];
const DIFFICULTY_OPTIONS: { value: string; label: string }[] = [
  { value: "easy", label: "Dễ" },
  { value: "medium", label: "Vừa" },
  { value: "hard", label: "Khó" },
  { value: "mixed", label: "Trộn" },
];

interface QuizOptionsValue {
  quantity: number;
  difficulty: string;
}

interface QuizOptionsPanelProps {
  value: QuizOptionsValue;
  onChange: (value: QuizOptionsValue) => void;
  onSubmit: () => void;
  busy: boolean;
  submitLabel: string;
  progress?: number;
  documentProcessing?: boolean;
}

export function QuizOptionsPanel({
  value,
  onChange,
  onSubmit,
  busy,
  submitLabel,
  progress = 0,
  documentProcessing = false,
}: QuizOptionsPanelProps) {
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
          Số câu hỏi
        </span>
        <div className="grid grid-cols-3 gap-2">
          {QUANTITY_OPTIONS.map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => onChange({ ...value, quantity: n })}
              disabled={busy}
              className={cn(
                "rounded-lg border py-2 text-sm font-semibold transition-colors",
                value.quantity === n
                  ? "border-primary bg-primary/10 text-primary shadow-[var(--shadow-xs)]"
                  : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              {n} câu
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Độ khó
        </span>
        <div className="grid grid-cols-4 gap-2">
          {DIFFICULTY_OPTIONS.map((d) => (
            <button
              key={d.value}
              type="button"
              onClick={() => onChange({ ...value, difficulty: d.value })}
              disabled={busy}
              className={cn(
                "rounded-lg border py-2 text-sm font-semibold transition-colors",
                value.difficulty === d.value
                  ? "border-primary bg-primary/10 text-primary shadow-[var(--shadow-xs)]"
                  : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {busy ? (
        <div className="space-y-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <Button disabled size="lg" className="w-full gap-2 font-semibold">
            <RefreshCw className="h-5 w-5 animate-spin" /> Đang tạo trắc nghiệm ({progress}%)…
          </Button>
        </div>
      ) : documentProcessing ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border/60 py-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Tài liệu đang được xử lý, vui lòng đợi...
        </div>
      ) : (
        <Button type="submit" size="lg" className="w-full gap-2 font-semibold">
          <HelpCircle className="h-5 w-5" />
          {submitLabel}
        </Button>
      )}
    </form>
  );
}
