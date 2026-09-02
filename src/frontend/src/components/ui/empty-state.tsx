"use client";

import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  badge?: string;
  expandable?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  badge = "Sắp ra mắt",
  expandable = false,
  className,
  children,
}: EmptyStateProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={cn(
        "mx-auto flex flex-col items-center justify-center gap-4 py-10 text-center transition-all animate-in fade-in-50",
        expandable && isExpanded ? "max-w-5xl" : "max-w-2xl",
        className
      )}
    >
      {expandable && children && (
        <div className="flex w-full justify-end">
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => setIsExpanded((prev) => !prev)}
          >
            {isExpanded ? "Thu gọn" : "Mở rộng"}
          </Button>
        </div>
      )}
      <Icon className="h-9 w-9 text-primary" aria-hidden="true" />
      <div className="space-y-2">
        <h3 className="font-display flex flex-wrap items-center justify-center gap-2 text-2xl font-semibold text-foreground">
          {title}
          {badge && (
            <span className="rounded-full border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
              {badge}
            </span>
          )}
        </h3>
        <p className="text-sm leading-relaxed text-muted-foreground sm:text-base">
          {description}
        </p>
      </div>
      {children}
    </div>
  );
}
