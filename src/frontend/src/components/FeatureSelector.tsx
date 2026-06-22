"use client";

import React from "react";
import {
  BookOpen,
  FileText,
  StickyNote,
  HelpCircle,
  Presentation,
  Map,
  Sparkles,
} from "lucide-react";

export type FeatureType =
  | "course"
  | "summary"
  | "flashcards"
  | "quiz"
  | "slides"
  | "mindmap"
  | "custom";

interface FeatureOption {
  type: FeatureType;
  label: string;
  description: string;
  icon: React.ReactNode;
}

const FEATURES: FeatureOption[] = [
  {
    type: "course",
    label: "Khóa học",
    description: "Tạo cấu trúc khóa học với chương và bài học",
    icon: <BookOpen className="h-5 w-5" />,
  },
  {
    type: "summary",
    label: "Tóm tắt",
    description: "Tóm tắt nội dung chính từ tài liệu",
    icon: <FileText className="h-5 w-5" />,
  },
  {
    type: "flashcards",
    label: "Flashcard",
    description: "Tạo flashcard để ghi nhớ kiến thức",
    icon: <StickyNote className="h-5 w-5" />,
  },
  {
    type: "quiz",
    label: "Quiz",
    description: "Tạo câu hỏi trắc nghiệm từ nội dung",
    icon: <HelpCircle className="h-5 w-5" />,
  },
  {
    type: "slides",
    label: "Slide",
    description: "Tạo nội dung slide thuyết trình",
    icon: <Presentation className="h-5 w-5" />,
  },
  {
    type: "mindmap",
    label: "Mind Map",
    description: "Vẽ sơ đồ tư duy hệ thống kiến thức",
    icon: <Map className="h-5 w-5" />,
  },
  {
    type: "custom",
    label: "Prompt riêng",
    description: "Nhập yêu cầu tùy chỉnh cho AI",
    icon: <Sparkles className="h-5 w-5" />,
  },
];

interface FeatureSelectorProps {
  selected: FeatureType | null;
  onSelect: (feature: FeatureType) => void;
}

export default function FeatureSelector({
  selected,
  onSelect,
}: FeatureSelectorProps) {
  return (
    <div className="w-full">
      <h3 className="text-lg font-semibold mb-4">Chọn tính năng</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {FEATURES.map((feature) => {
          const isSelected = selected === feature.type;
          return (
            <button
              key={feature.type}
              onClick={() => onSelect(feature.type)}
              className={`flex flex-col items-start text-left p-4 rounded-lg border transition-all cursor-pointer
                ${
                  isSelected
                    ? "border-primary bg-primary/10 ring-2 ring-primary/30"
                    : "border-muted-foreground/20 hover:border-muted-foreground/40 hover:bg-muted/50"
                }`}
            >
              <div
                className={`p-2 rounded-full mb-2 ${
                  isSelected
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {feature.icon}
              </div>
              <span className="font-medium text-sm">{feature.label}</span>
              <span className="text-xs text-muted-foreground mt-1 leading-tight">
                {feature.description}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}