"use client";

import type { LucideIcon } from "lucide-react";
import { Film, Loader2, MonitorPlay, RefreshCw, Smartphone, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FORMAT_OPTIONS: { value: string; label: string; hint: string; icon: LucideIcon }[] = [
  { value: "shorts", label: "Shorts", hint: "9:16 · 30-60s", icon: Smartphone },
  { value: "overview", label: "Tổng quan", hint: "16:9 · 2-3 phút", icon: Film },
  { value: "standard", label: "Tiêu chuẩn", hint: "16:9 · 5-7 phút", icon: MonitorPlay },
];

const VOICE_OPTIONS: { value: string; label: string }[] = [
  { value: "female", label: "Giọng nữ" },
  { value: "male", label: "Giọng nam" },
];

interface VidOptionsValue {
  format: string;
  voice: string;
  userPrompt: string;
}

interface VidOptionsPanelProps {
  value: VidOptionsValue;
  onChange: (value: VidOptionsValue) => void;
  onSubmit: () => void;
  busy: boolean;
  submitLabel: string;
  progress?: number;
  documentProcessing?: boolean;
}

export function VidOptionsPanel({
  value,
  onChange,
  onSubmit,
  busy,
  submitLabel,
  progress = 0,
  documentProcessing = false,
}: VidOptionsPanelProps) {
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
          Định dạng
        </span>
        <div className="grid grid-cols-3 gap-2">
          {FORMAT_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => onChange({ ...value, format: opt.value })}
                disabled={busy}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-lg border py-3 text-xs font-semibold transition-colors",
                  value.format === opt.value
                    ? "border-primary bg-primary/10 text-primary shadow-[var(--shadow-xs)]"
                    : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {opt.label}
                <span className="text-[10px] font-normal opacity-80">{opt.hint}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Giọng đọc
        </span>
        <div className="grid grid-cols-2 gap-2">
          {VOICE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange({ ...value, voice: opt.value })}
              disabled={busy}
              className={cn(
                "rounded-lg border py-2 text-sm font-semibold transition-colors",
                value.voice === opt.value
                  ? "border-primary bg-primary/10 text-primary shadow-[var(--shadow-xs)]"
                  : "border-border/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              {opt.label}
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
          placeholder="Ví dụ: tập trung vào phần ứng dụng thực tế…"
          rows={2}
          className="w-full resize-none rounded-lg border border-border/60 bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none"
        />
      </div>

      {busy ? (
        <div className="space-y-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <Button disabled size="lg" className="w-full gap-2 font-semibold">
            <RefreshCw className="h-5 w-5 animate-spin" /> Đang dựng video ({progress}%)…
          </Button>
        </div>
      ) : documentProcessing ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border/60 py-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Tài liệu đang được xử lý, vui lòng đợi...
        </div>
      ) : (
        <Button type="submit" size="lg" className="w-full gap-2 font-semibold">
          <Video className="h-5 w-5" />
          {submitLabel}
        </Button>
      )}
    </form>
  );
}
