"use client";

import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { usePollingArtifact } from "@/hooks/usePollingArtifact";
import {
  Presentation,
  Download,
  FileText,
  Maximize2,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  X,
  Images,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { SlideOptionsPanel } from "@/components/dashboard/SlideOptionsPanel";
import { CreateVersionButton } from "@/components/dashboard/CreateVersionButton";
import { VersionSwitcher } from "@/components/dashboard/VersionSwitcher";
import { JobProgress } from "@/components/dashboard/JobProgress";
import {
  ApiRequestError,
  apiDeleteArtifactVersion,
  apiGetSlide,
  apiGenerateSlide,
  apiRenameArtifactVersion,
  getDownloadSlideUrl,
  getDownloadSlidePdfUrl,
  getSlideImageUrl,
} from "@/lib/api";
import type { SlidesOutput } from "@/lib/types";

interface SlideTabProps {
  courseId: string;
  /** True while the course's document is still being extracted/indexed — generating now
   * would hit the backend's "still processing" guard, so the button is disabled instead. */
  documentProcessing?: boolean;
}

export function SlideTab({ courseId, documentProcessing = false }: SlideTabProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPresenterMode, setIsPresenterMode] = useState(false);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [regenDialogOpen, setRegenDialogOpen] = useState(false);
  const [mode, setMode] = useState<"summary" | "lesson" | "deep_dive">("lesson");
  const [focusPrompt, setFocusPrompt] = useState("");
  const stageRef = useRef<HTMLDivElement>(null);
  const downloadMenuRef = useRef<HTMLDivElement>(null);

  const {
    data: deck,
    hasFetched,
    error,
    setError,
    generating,
    setGenerating,
    progress,
    setProgress,
    activeJob,
    startJob,
    finishJob,
    prepareActiveJobRetry,
    consumeJobRetryVersion,
    clearJobRetryVersion,
    resumeArtifactPolling,
    versions,
    activeVersion,
    viewedVersion,
    switchVersion,
    refresh,
  } = usePollingArtifact<SlidesOutput>({
    courseId,
    fetchFn: apiGetSlide,
    isReady: (data) => (data.slides?.length ?? 0) > 0,
    timeoutMs: 3 * 60 * 1000,
    timeoutMessage: "Quá trình tạo slide mất nhiều thời gian hơn dự kiến. Vui lòng thử lại sau.",
    defaultErrorMessage: "Tạo slide thất bại.",
    onReady: () => setCurrentIndex(0),
  });

  const loading = !hasFetched && !error;

  // Close download menu on outside click
  useEffect(() => {
    if (!downloadMenuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (downloadMenuRef.current && !downloadMenuRef.current.contains(e.target as Node)) {
        setDownloadMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [downloadMenuOpen]);

  // Keyboard Arrow Key Navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA"].includes((e.target as HTMLElement)?.tagName)) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        setCurrentIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === "ArrowRight" || e.key === "ArrowDown" || e.key === " ") {
        if (!deck?.slides) return;
        setCurrentIndex((prev) => Math.min(deck.slides.length - 1, prev + 1));
      } else if (e.key === "Escape" && isPresenterMode) {
        setIsPresenterMode(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [deck?.slides, isPresenterMode]);

  const handleGenerate = async () => {
    const retryVersionId = consumeJobRetryVersion();
    setGenerating(true);
    setError(null);
    setProgress(5);
    try {
      const res = await apiGenerateSlide(courseId, {
        mode,
        focus_prompt: focusPrompt,
        ...(retryVersionId ? { retry_version_id: retryVersionId } : {}),
      });
      startJob(res.job_id, res.version_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bắt đầu tạo slide thất bại.");
      setGenerating(false);
    }
  };

  // The backend persists a hard "error" status from the last generation attempt, so a plain
  // refetch would just surface the same error forever — retry opens the picker before a new job.
  const handleRetryAfterError = () => {
    clearJobRetryVersion();
    setRegenDialogOpen(true);
  };
  const handleRenameVersion = async (versionId: string, label: string) => {
    try { await apiRenameArtifactVersion(courseId, "slides", versionId, label); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể đổi tên phiên bản."); }
  };
  const handleDeleteVersion = async (versionId: string) => {
    if (!window.confirm("Xóa phiên bản này? Thao tác không thể hoàn tác.")) return;
    try { await apiDeleteArtifactVersion(courseId, "slides", versionId); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể xóa phiên bản."); }
  };

  // Regenerating from the ready view keeps the current deck visible (stale-while-revalidate)
  // instead of bouncing to the full-page ErrorState/EmptyState — a 429 (regen limit reached)
  // surfaces as a small inline banner instead of blowing away otherwise-valid content.
  const handleCreateVersion = async (retryVersionId: string | null = null) => {
    setRegenError(null);
    setGenerating(true);
    setProgress(5);
    try {
      const res = await apiGenerateSlide(courseId, {
        mode,
        focus_prompt: focusPrompt,
        ...(retryVersionId ? { retry_version_id: retryVersionId } : {}),
      });
      startJob(res.job_id, res.version_id);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 409 && (err.detail as { code?: string })?.code === "version_cap_reached") {
        toast.error("Tối đa 3 phiên bản. Hãy xóa một phiên bản để tạo bản mới.");
        setGenerating(false);
        return;
      }
      setRegenError(err instanceof Error ? err.message : "Tạo phiên bản mới thất bại.");
      setGenerating(false);
    }
  };

  const optionValue = { mode, focusPrompt };
  const updateOptions = (value: typeof optionValue) => {
    setMode(value.mode);
    setFocusPrompt(value.focusPrompt);
  };
  const submitRegenerateFromDialog = () => {
    const retryVersionId = consumeJobRetryVersion() ?? (error ? viewedVersion : null);
    setRegenDialogOpen(false);
    void handleCreateVersion(retryVersionId);
  };
  const openFreshVersionDialog = () => {
    clearJobRetryVersion();
    setRegenError(null);
    setRegenDialogOpen(true);
  };
  const closeRegenerateDialog = () => {
    clearJobRetryVersion();
    setRegenDialogOpen(false);
  };
  const regenerateDialog = (
    <Dialog open={regenDialogOpen} onOpenChange={(open) => open ? setRegenDialogOpen(true) : closeRegenerateDialog()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Tạo phiên bản slide mới</DialogTitle>
          <DialogDescription>
            Xác nhận để bắt đầu tạo bộ slide mới. Nội dung hiện tại vẫn được giữ cho đến khi bản mới sẵn sàng.
          </DialogDescription>
        </DialogHeader>
        <SlideOptionsPanel
          value={optionValue}
          onChange={updateOptions}
          onSubmit={submitRegenerateFromDialog}
          busy={generating}
          progress={progress}
          submitLabel="Tạo phiên bản mới"
          documentProcessing={documentProcessing}
        />
        <DialogFooter>
          <Button variant="ghost" onClick={closeRegenerateDialog}>
            Hủy
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
  const jobProgress = activeJob ? (
    <JobProgress
      key={activeJob.jobId}
      jobId={activeJob.jobId}
      onSucceeded={resumeArtifactPolling}
      onTerminal={finishJob}
      onRetry={() => {
        prepareActiveJobRetry();
        setRegenDialogOpen(true);
      }}
    />
  ) : null;

  const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
      stageRef.current?.requestFullscreen().catch((err) => {
        console.error("Error attempting to enable full-screen mode:", err);
      });
      setIsPresenterMode(true);
    } else {
      document.exitFullscreen();
      setIsPresenterMode(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6 py-6 animate-pulse">
        <div className="flex justify-between items-center">
          <Skeleton className="h-8 w-64 rounded-xl" />
          <div className="flex gap-2">
            <Skeleton className="h-10 w-32 rounded-xl" />
            <Skeleton className="h-10 w-36 rounded-xl" />
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-1 space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-24 w-full rounded-xl" />
            ))}
          </div>
          <div className="lg:col-span-3">
            <Skeleton className="aspect-video w-full rounded-2xl" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <>
        <ErrorState
          title="Lỗi tạo bài giảng"
          description={error}
          onRetry={handleRetryAfterError}
          retryLabel="Mở tùy chọn tạo mới"
        />
        {regenerateDialog}
      </>
    );
  }

  if (!deck || !deck.slides || deck.slides.length === 0) {
    return (
      <EmptyState
        icon={Presentation}
        title="Chưa có slide bài giảng"
        description="Hệ thống sẽ phân tích tài liệu của bạn và tạo bộ slide trình chiếu chuẩn 16:9 (khoảng 15 trang) bám sát nội dung."
        badge=""
      >
        {jobProgress ?? (
          <SlideOptionsPanel
            value={optionValue}
            onChange={updateOptions}
            onSubmit={handleGenerate}
            busy={generating}
            progress={progress}
            submitLabel="Tạo slide bài giảng"
            documentProcessing={documentProcessing}
          />
        )}
      </EmptyState>
    );
  }

  const slides = deck.slides;

  // PRESENTER FULLSCREEN MODE — minimal chrome: image, prev/next, page count, exit.
  if (isPresenterMode) {
    return (
      <>
        <div className="hidden">{jobProgress}</div>
        <div
          ref={stageRef}
          className="fixed inset-0 z-50 bg-stage text-stage-foreground flex flex-col items-center justify-center select-none overflow-hidden animate-in fade-in duration-200"
        >
        <button
          onClick={() => {
            if (document.fullscreenElement) document.exitFullscreen();
            setIsPresenterMode(false);
          }}
          className="absolute top-4 right-4 p-2 rounded-lg bg-stage-muted hover:bg-stage-border text-stage-foreground transition-colors"
          title="Thoát trình chiếu"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="w-full h-full max-h-full aspect-video mx-auto flex items-center justify-center px-4">
          <img
            src={getSlideImageUrl(courseId, currentIndex + 1)}
            alt={`Slide ${currentIndex + 1}`}
            className="w-full h-full object-contain"
          />
        </div>

        <div className="absolute inset-x-0 bottom-6 flex items-center justify-center gap-4">
          <button
            onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
            disabled={currentIndex === 0}
            className="p-2 rounded-lg bg-stage-muted hover:bg-stage-border text-stage-foreground disabled:opacity-40 transition-colors"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="font-mono text-sm font-semibold text-stage-foreground px-2">
            {currentIndex + 1} / {slides.length}
          </span>
          <button
            onClick={() => setCurrentIndex((prev) => Math.min(slides.length - 1, prev + 1))}
            disabled={currentIndex === slides.length - 1}
            className="p-2 rounded-lg bg-stage-muted hover:bg-stage-border text-stage-foreground disabled:opacity-40 transition-colors"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
        </div>
      </>
    );
  }

  // STANDARD BROWSER PREVIEW & WORKSPACE
  return (
    <div className="space-y-6 animate-in fade-in-50">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card/40 p-5 rounded-2xl border shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
            <Presentation className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-semibold text-foreground tracking-tight truncate">
              {deck.title || "Bài giảng trình chiếu"}
            </h2>
            <span className="text-xs text-muted-foreground">{slides.length} slide</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="relative" ref={downloadMenuRef}>
            <Button
              onClick={() => setDownloadMenuOpen((v) => !v)}
              variant="default"
              className="gap-1.5"
            >
              <Download className="h-4 w-4" />
              Tải xuống
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
            {downloadMenuOpen && (
              <div className="absolute right-0 top-full mt-1.5 w-40 rounded-xl border bg-card p-1 shadow-[var(--shadow-md)] z-10 animate-in fade-in-50">
                <a
                  href={getDownloadSlideUrl(courseId, viewedVersion)}
                  target="_blank"
                  rel="noopener noreferrer"
                  download
                  onClick={() => setDownloadMenuOpen(false)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  <Download className="h-3.5 w-3.5" /> PPTX
                </a>
                <a
                  href={getDownloadSlidePdfUrl(courseId, viewedVersion)}
                  target="_blank"
                  rel="noopener noreferrer"
                  download
                  onClick={() => setDownloadMenuOpen(false)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  <FileText className="h-3.5 w-3.5" /> PDF
                </a>
              </div>
            )}
          </div>

          <Button onClick={toggleFullScreen} variant="outline" className="gap-1.5">
            <Maximize2 className="h-4 w-4" />
            <span className="hidden sm:inline">Trình chiếu</span>
          </Button>

          {generating ? (
            <Button disabled variant="outline" className="gap-1.5">
              <RefreshCw className="h-4 w-4 animate-spin" /> Đang tạo ({progress}%)…
            </Button>
          ) : (
            <CreateVersionButton
              label="bộ slide"
              onOpen={openFreshVersionDialog}
            />
          )}
        </div>
      </div>

      {jobProgress}

      <VersionSwitcher versions={versions} activeVersion={activeVersion} viewedVersion={viewedVersion} onSwitch={switchVersion} onCreate={openFreshVersionDialog} onRename={handleRenameVersion} onDelete={handleDeleteVersion} />

      {regenError && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-error/40 bg-error/5 px-4 py-3 text-sm text-error">
          <span>{regenError}</span>
          <button onClick={() => setRegenError(null)} className="shrink-0 font-semibold hover:underline">
            Đóng
          </button>
        </div>
      )}

      {regenerateDialog}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Sidebar: Thumbnails List */}
        <div className="lg:col-span-1 space-y-3 max-h-[620px] overflow-y-auto pr-1">
          <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground px-1">
            <Images className="h-3.5 w-3.5" /> Danh sách Slide ({slides.length})
          </span>
          {slides.map((sl, idx) => {
            const isSelected = idx === currentIndex;
            return (
              <div
                key={idx}
                onClick={() => setCurrentIndex(idx)}
                className={cn(
                  "group rounded-xl border-2 transition-all cursor-pointer bg-card hover:border-primary/50 flex flex-col relative overflow-hidden aspect-video shadow-[var(--shadow-xs)]",
                  isSelected
                    ? "border-primary bg-primary/5 shadow-[var(--shadow-md)] ring-2 ring-primary/20"
                    : "border-border/60 opacity-80 hover:opacity-100"
                )}
              >
                <img
                  src={getSlideImageUrl(courseId, idx + 1)}
                  alt={`Slide ${idx + 1}`}
                  className="w-full h-full object-cover"
                />
                <div className="absolute bottom-1 left-1 bg-black/75 px-1.5 py-0.5 rounded text-[10px] text-white font-bold">
                  #{idx + 1}
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: 16:9 Widescreen Presentation Stage */}
        <div className="lg:col-span-3 space-y-4">
          <div className="w-full aspect-video bg-stage border border-stage-border rounded-2xl shadow-2xl relative overflow-hidden text-stage-foreground flex items-center justify-center">
            <img
              src={getSlideImageUrl(courseId, currentIndex + 1)}
              alt={`Slide ${currentIndex + 1}`}
              className="w-full h-full object-contain"
            />
          </div>

          {/* Below Stage: Navigation Bar */}
          <div className="flex items-center justify-between bg-card/60 p-4 rounded-xl border shadow-[var(--shadow-xs)]">
            <Button
              variant="outline"
              onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
              disabled={currentIndex === 0}
              className="gap-1 font-medium text-xs"
            >
              <ChevronLeft className="h-4 w-4" /> Slide trước
            </Button>

            <span className="font-bold text-sm text-foreground">
              Trang {currentIndex + 1} / {slides.length}
            </span>

            <Button
              variant="outline"
              onClick={() => setCurrentIndex((prev) => Math.min(slides.length - 1, prev + 1))}
              disabled={currentIndex === slides.length - 1}
              className="gap-1 font-medium text-xs"
            >
              Slide tiếp <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
