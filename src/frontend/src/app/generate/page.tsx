"use client";

import { useState } from "react";
import { toast } from "sonner";
import UploadBox from "@/components/UploadBox";
import FeatureSelector, { type FeatureType } from "@/components/FeatureSelector";
import PromptInput from "@/components/PromptInput";
import { FileText, BookOpen, Sparkles } from "lucide-react";

export default function GeneratePage() {
  const [selectedFeature, setSelectedFeature] = useState<FeatureType | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handlePromptSubmit = async (prompt: string) => {
    if (!selectedFeature) {
      toast.error("Vui lòng chọn một tính năng trước khi gửi yêu cầu.");
      return;
    }

    setIsProcessing(true);
    // TODO: Call API endpoint based on selectedFeature and prompt
    // e.g. if (selectedFeature === "course") await generateCourse(prompt);
    console.log("Processing:", { feature: selectedFeature, prompt });
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 2000));
    setIsProcessing(false);
  };

  return (
    <div className="flex flex-col items-center min-h-screen py-8 px-4">
      {/* Hero Section */}
      <div className="text-center max-w-2xl mb-8">
        <div className="inline-flex items-center justify-center p-2 bg-primary/10 rounded-full mb-4">
          <Sparkles className="h-6 w-6 text-primary" />
        </div>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl mb-4">
          Tạo Nội Dung Từ Tài Liệu Của Bạn
        </h1>
        <p className="text-muted-foreground text-lg">
          Tải lên PDF, DOCX hoặc TXT, chọn tính năng và để AI tự động tạo nội dung
          học tập cho bạn.
        </p>
      </div>

      {/* How it works */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-2xl mb-8">
        <div className="flex flex-col items-center text-center p-4 rounded-lg border bg-card">
          <div className="p-2 bg-primary/10 rounded-full mb-3">
            <FileText className="h-5 w-5 text-primary" />
          </div>
          <h3 className="font-semibold text-sm mb-1">1. Tải lên tài liệu</h3>
          <p className="text-xs text-muted-foreground">
            PDF, DOCX hoặc TXT
          </p>
        </div>
        <div className="flex flex-col items-center text-center p-4 rounded-lg border bg-card">
          <div className="p-2 bg-primary/10 rounded-full mb-3">
            <Sparkles className="h-5 w-5 text-primary" />
          </div>
          <h3 className="font-semibold text-sm mb-1">2. Chọn tính năng</h3>
          <p className="text-xs text-muted-foreground">
            Course, Summary, Flashcard, Quiz, Slide hoặc Mind Map
          </p>
        </div>
        <div className="flex flex-col items-center text-center p-4 rounded-lg border bg-card">
          <div className="p-2 bg-primary/10 rounded-full mb-3">
            <BookOpen className="h-5 w-5 text-primary" />
          </div>
          <h3 className="font-semibold text-sm mb-1">3. Nhận kết quả</h3>
          <p className="text-xs text-muted-foreground">
            AI xử lý và trả nội dung ngay lập tức
          </p>
        </div>
      </div>

      {/* Upload Component */}
      <div className="w-full max-w-2xl mb-8">
        <UploadBox />
      </div>

      {/* Feature Selector */}
      <div className="w-full max-w-3xl mb-8">
        <FeatureSelector
          selected={selectedFeature}
          onSelect={setSelectedFeature}
        />
      </div>

      {/* Prompt Input */}
      <div className="w-full max-w-3xl mb-8">
        <PromptInput
          onSubmit={handlePromptSubmit}
          isLoading={isProcessing}
          disabled={!selectedFeature}
        />
      </div>
    </div>
  );
}
