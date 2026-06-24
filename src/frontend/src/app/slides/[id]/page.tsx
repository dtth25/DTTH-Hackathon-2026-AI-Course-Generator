"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, Download, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui";
import { generateSlides, type SlidesResponse } from "@/lib/api";

/* ── Component ─────────────────────────────────────────── */

export default function SlidesPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.id as string;

  const [slides, setSlides] = useState<SlidesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [presentOpen, setPresentOpen] = useState(false);
  const [iframeError, setIframeError] = useState(false);
  const [slideHtml, setSlideHtml] = useState<string | null>(null);
  const slideRef = useRef<HTMLDivElement>(null);

  /* Fetch slides on mount */
  useEffect(() => {
    async function fetchSlides() {
      try {
        setLoading(true);
        setError(null);
        const data = await generateSlides(courseId);
        setSlides(data);

         // Fetch backend-generated HTML (generate_slide_html) and store for presenter
         try {
          const resp = await fetch(`/api/course/${courseId}/slides/html`);
          if (resp.ok) {
            const html = await resp.text();
            setSlideHtml(html);
          } else {
            setSlideHtml(null);
          }
         } catch {
           setSlideHtml(null);
         }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Không thể tải slides."
        );
      } finally {
        setLoading(false);
      }
    }
    fetchSlides();
  }, [courseId]);

  /* Keyboard navigation */
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!slides) return;
      if (e.key === "ArrowRight" || e.key === "ArrowDown" || e.key === " ") {
        e.preventDefault();
        goToSlide(currentSlide + 1);
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        goToSlide(currentSlide - 1);
      } else if (e.key === "f" || e.key === "F") {
        toggleFullscreen();
      } else if (e.key === "Escape") {
        setFullscreen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentSlide, slides, fullscreen]);

  /* Fullscreen toggle */
  const toggleFullscreen = useCallback(async () => {
    if (!fullscreen) {
      try {
        await slideRef.current?.requestFullscreen();
        setFullscreen(true);
      } catch {
        // fallback: just toggle state
        setFullscreen(true);
      }
    } else {
      try {
        await document.exitFullscreen();
        setFullscreen(false);
      } catch {
        setFullscreen(false);
      }
    }
  }, [fullscreen]);

  /* Listen to fullscreen change */
  useEffect(() => {
    const handleChange = () => {
      setFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", handleChange);
    return () => document.removeEventListener("fullscreenchange", handleChange);
  }, []);

  /* Navigation */
  const goToSlide = useCallback(
    (index: number) => {
      if (!slides) return;
      setCurrentSlide(Math.max(0, Math.min(index, slides.slides.length - 1)));
    },
    [slides]
  );

  /* Render slide content HTML */
  const renderContent = (content: string) => {
    let html = content
      .replace(/^### (.*$)/gm, "<h3>$1</h3>")
      .replace(/^## (.*$)/gm, "<h2>$1</h2>")
      .replace(/^# (.*$)/gm, "<h1>$1</h1>")
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em>$1</em>")
      .replace(/^- (.*$)/gm, "<li>$1</li>")
      .replace(/\n/g, "<br/>");
    return html;
  };

  /* ── Loading state ── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Đang tạo slides...</p>
      </div>
    );
  }

  /* ── Error state ── */
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

  /* ── Empty state ── */
  if (!slides || slides.slides.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <p className="text-sm text-muted-foreground">Chưa có slides.</p>
        <Button variant="outline" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  const totalSlides = slides.slides.length;
  const currentData = slides.slides[currentSlide];

  /* ── Main render ── */
  return (
    <div
      className={`flex flex-col ${fullscreen ? "fixed inset-0 z-50 bg-background" : "min-h-[80vh]"}`}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30 shrink-0">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ChevronLeft className="h-4 w-4 mr-1" />
            Thoát
          </Button>
          <Button size="sm" onClick={() => setPresentOpen(true)}>
            ▶ Present
          </Button>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>
            {currentSlide + 1} / {totalSlides}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToSlide(currentSlide - 1)}
            disabled={currentSlide === 0}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToSlide(currentSlide + 1)}
            disabled={currentSlide === totalSlides - 1}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={toggleFullscreen}>
            {fullscreen ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Reveal.js presentation via backend HTML */}
      {presentOpen && (
        <div className="fixed inset-0 z-50 bg-black text-white">
          <div className="absolute top-3 right-3 z-50 flex gap-2">
            <button
              onClick={() => setPresentOpen(false)}
              className="rounded bg-white/10 px-3 py-1 text-sm backdrop-blur hover:bg-white/20"
            >
              ✕ Đóng
            </button>
          </div>

          {!iframeError ? (
            // Use fetched HTML as srcDoc so presenter uses the exact backend HTML
            slideHtml ? (
              <iframe
                srcDoc={slideHtml}
                onError={() => setIframeError(true)}
                className="h-full w-full border-0"
                allow="autoplay; fullscreen"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            )
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-center">
              <AlertCircle className="h-10 w-10" />
              <p className="text-sm">Không tải được slides. Mở trang slides để xem bản thường.</p>
              <Button variant="outline" onClick={() => router.back()}>Quay lại</Button>
            </div>
          )}
        </div>
      )}

      {/* Slide content area */}
      <div
        ref={slideRef}
        className={`flex-1 overflow-auto ${fullscreen ? "fixed inset-0 z-50 bg-white" : "min-h-[80vh]"}`}
      >
        <div className="mx-auto max-w-3xl px-6 py-10 md:px-12">
          {currentSlide === 0 ? (
            <div className="mb-10 border-b pb-8">
              <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-indigo-500">
                AI Course Generator
              </div>
              <h1 className="font-serif text-3xl font-bold leading-tight md:text-4xl">
                {currentData.title}
              </h1>
              <div className="mt-4 h-1 w-16 bg-indigo-500" />
            </div>
          ) : (
            <h2 className="mb-6 font-serif text-2xl font-bold text-slate-900 md:text-3xl">
              {currentData.title}
            </h2>
          )}

          <div
            className="prose max-w-none text-slate-700"
            dangerouslySetInnerHTML={{
              __html: renderContent(currentData.content || ""),
            }}
          />

          {currentData.citation && (
            <div className="mt-10 border-t border-slate-200 pt-4 text-center text-xs text-slate-500">
              📖 Nguồn: Trang {currentData.citation.page} — {currentData.citation.source} (chunk:{" "}
              {currentData.citation.chunk_id})
            </div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-muted shrink-0">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{
            width: `${((currentSlide + 1) / totalSlides) * 100}%`,
          }}
        />
      </div>
    </div>
  );
}