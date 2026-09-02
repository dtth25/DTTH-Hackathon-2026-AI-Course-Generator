"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title: string;
  description: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  onAction?: () => void;
  actionLabel?: string;
  actionDisabled?: boolean;
  actionIcon?: ReactNode;
  className?: string;
}

export function ErrorState({
  title,
  description,
  onRetry,
  retryLabel = "Thử lại",
  onAction,
  actionLabel,
  actionDisabled = false,
  actionIcon,
  className,
}: ErrorStateProps) {
  const action = onAction ?? onRetry;
  const label = actionLabel ?? retryLabel;
  return (
    <Card className={cn("my-6 border-error/30 bg-error/5 p-8 text-center", className)}>
      <CardHeader>
        <AlertCircle className="mx-auto mb-2 h-12 w-12 text-error" />
        <CardTitle className="text-xl text-error">{title}</CardTitle>
        <CardDescription className="mt-1 text-sm">{description}</CardDescription>
      </CardHeader>
      {action && (
        <CardFooter className="justify-center pt-2">
          <Button onClick={action} disabled={actionDisabled} variant="outline" className="gap-2">
            {actionIcon ?? <RefreshCw className="h-4 w-4" />} {label}
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}
