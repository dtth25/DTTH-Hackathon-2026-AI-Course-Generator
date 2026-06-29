"use client";

import React, { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

interface PromptInputProps {
  onSubmit: (prompt: string) => void;
  isLoading: boolean;
  disabled?: boolean;
}

const PLACEHOLDER = 'Ví dụ: "Tập trung vào phần nhập môn"';

export default function PromptInput({
  onSubmit,
  isLoading,
  disabled = false,
}: PromptInputProps) {
  const [prompt, setPrompt] = useState("");

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onSubmit(prompt.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <h3 className="mb-3 text-lg font-semibold">Yêu cầu thêm</h3>
      <div className="space-y-3">
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={PLACEHOLDER}
          disabled={disabled}
          rows={3}
          className="flex w-full resize-none rounded-lg border border-input bg-background px-4 py-3 text-sm shadow-sm placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        />
        <Button
          type="submit"
          disabled={disabled || isLoading}
          className="w-full"
          size="lg"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Đang tạo
            </>
          ) : (
            <>
              <Sparkles className="mr-2 h-4 w-4" />
              Tạo output
            </>
          )}
        </Button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Có thể để trống để hệ thống tự chọn trọng tâm phù hợp với tài liệu.
      </p>
    </form>
  );
}
