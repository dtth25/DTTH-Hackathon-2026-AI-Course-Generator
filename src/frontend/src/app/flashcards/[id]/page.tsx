"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  Shuffle,
  RotateCw,
  Loader2,
  AlertCircle,
  Lightbulb,
} from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Button,
  Progress,
} from "@/components/ui";
import { generateFlashcards, type FlashcardsResponse } from "@/lib/api";

export default function FlashcardsPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.id as string;

  const [data, setData] = useState<FlashcardsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);

  useEffect(() => {
    async function fetchFlashcards() {
      try {
        setLoading(true);
        setError(null);
        const result = await generateFlashcards(courseId, 12);
        setData(result);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Không thể tải flashcards."
        );
      } finally {
        setLoading(false);
      }
    }
    fetchFlashcards();
  }, [courseId]);

  const goTo = useCallback(
    (index: number) => {
      if (!data) return;
      const total = data.flashcards.length;
      setCurrentIndex(((index % total) + total) % total);
      setFlipped(false);
    },
    [data]
  );

  const shuffle = useCallback(() => {
    if (!data) return;
    const randomIndex = Math.floor(Math.random() * data.flashcards.length);
    goTo(randomIndex);
  }, [data, goTo]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Đang tạo flashcards...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-sm text-destructive font-medium">{error}</p>
        <Button variant="outline" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  if (!data || data.flashcards.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <p className="text-sm text-muted-foreground">Chưa có flashcards.</p>
        <Button variant="outline" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  const total = data.flashcards.length;
  const current = data.flashcards[currentIndex];

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Quay lại
        </button>
        <h1 className="text-2xl font-semibold tracking-tight">Flashcards</h1>
      </div>

      {/* Progress */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>
            {currentIndex + 1} / {total}
          </span>
        </div>
        <Progress value={((currentIndex + 1) / total) * 100} />
      </div>

      {/* Flashcard */}
      <div
        className="cursor-pointer"
        onClick={() => setFlipped(!flipped)}
      >
        <Card
          className={`min-h-[300px] transition-all duration-500 ${
            flipped ? "bg-muted/30" : ""
          }`}
        >
          <CardContent className="flex flex-col items-center justify-center min-h-[300px] p-8 text-center">
            {!flipped ? (
              <>
                <Lightbulb className="h-8 w-8 text-yellow-500 mb-4" />
                <p className="text-xl font-medium leading-relaxed">
                  {current.question}
                </p>
                <p className="text-xs text-muted-foreground mt-4">
                  Nhấn để xem đáp án
                </p>
              </>
            ) : (
              <>
                <p className="text-lg leading-relaxed text-muted-foreground">
                  {current.answer}
                </p>
                {current.citation && (
                  <div className="mt-6 text-xs text-muted-foreground border-t pt-4">
                    📖 Trang {current.citation.page} — {current.citation.source}
                    {current.citation.chunk_id && (
                      <> (chunk: {current.citation.chunk_id})</>
                    )}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between gap-3">
        <Button
          variant="outline"
          onClick={() => goTo(currentIndex - 1)}
          disabled={total <= 1}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Trước
        </Button>

        <Button variant="ghost" onClick={shuffle} disabled={total <= 1}>
          <Shuffle className="h-4 w-4 mr-1" />
          Ngẫu nhiên
        </Button>

        <Button
          variant="outline"
          onClick={() => goTo(currentIndex + 1)}
          disabled={total <= 1}
        >
          Sau
          <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}