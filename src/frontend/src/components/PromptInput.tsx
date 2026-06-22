"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Sparkles, Loader2 } from "lucide-react";

interface PromptInputProps {
  onSubmit: (prompt: string) => void;
  isLoading: boolean;
  disabled?: boolean;
}

const PLACEHOLDER_SUGGESTIONS = [
  'Ví dụ: "Tóm tắt tài liệu này trong 5 ý chính"',
  'Ví dụ: "Tạo quiz mức độ khó từ nội dung"',
  'Ví dụ: "Giải thích tài liệu cho học sinh cấp 3"',
  'Ví dụ: "Tạo flashcard để ôn tập nhanh"',
];

export default function PromptInput({
  onSubmit,
  isLoading,
  disabled = false,
}: PromptInputProps) {
  const [prompt, setPrompt] = useState("");
  const [placeholderIndex, setPlaceholderIndex] = useState(0);

  // Cycle placeholders on focus
  const handleFocus = () => {
    setPlaceholderIndex((prev) => (prev + 1) % PLACEHOLDER_SUGGESTIONS.length);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (prompt.trim()) {
      await onSubmit(prompt.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <h3 className="text-lg font-semibold mb-3">Nhập yêu cầu (tuỳ chọn)</h3>
      <div className="flex gap-3">
        <div className="relative flex-1">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onFocus={handleFocus}
            placeholder={PLACEHOLDER_SUGGESTIONS[placeholderIndex]}
            disabled={disabled}
            rows={2}
            className="flex w-full rounded-lg border border-input bg-background px-4 py-3 text-sm shadow-sm
              placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2
              focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-none"
          />
        </div>
        <Button
          type="submit"
          disabled={disabled || !prompt.trim() || isLoading}
          className="shrink-0 self-end"
          size="lg"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Đang xử lý...
            </>
          ) : (
            <>
              <Sparkles className="mr-2 h-4 w-4" />
              Gửi
            </>
          )}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground mt-2">
        Nhập yêu cầu cụ thể hoặc để trống để AI tự động tạo nội dung phù hợp.
      </p>
    </form>
  );
}