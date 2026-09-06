"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  BookOpen,
  RefreshCw,
  Download,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  Target,
  Star,
  HelpCircle,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { Markdown } from "@/components/ui/markdown";
import { BookOptionsPanel, BOOK_DETAIL_OPTIONS } from "@/components/dashboard/BookOptionsPanel";
import { CreateVersionButton } from "@/components/dashboard/CreateVersionButton";
import { VersionSwitcher } from "@/components/dashboard/VersionSwitcher";
import { JobProgress } from "@/components/dashboard/JobProgress";
import { ApiRequestError, apiDeleteArtifactVersion, apiGetBook, apiGenerateBook, apiRenameArtifactVersion, getDownloadBookUrl } from "@/lib/api";
import { usePollingArtifact } from "@/hooks/usePollingArtifact";
import { normalizePublicError, type BookOutput } from "@/lib/types";

interface BookTabProps {
  courseId: string;
  /** True while the course's document is still being extracted/indexed — generating now
   * would hit the backend's "still processing" guard, so the button is disabled instead. */
  documentProcessing?: boolean;
}

export function BookTab({ courseId, documentProcessing = false }: BookTabProps) {
  const [isFetching, setIsFetching] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1); // -1 = "Giới thiệu" pane
  const [isExpanded, setIsExpanded] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [regenDialogOpen, setRegenDialogOpen] = useState(false);

  // Generation config
  const [detailLevel, setDetailLevel] = useState(BOOK_DETAIL_OPTIONS[1]);
  const [userPrompt, setUserPrompt] = useState("");

  const {
    data: book,
    setData: setBook,
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
  } = usePollingArtifact<BookOutput>({
    courseId,
    fetchFn: apiGetBook,
    isReady: (data) => (data.chapters?.length ?? 0) > 0,
    timeoutMs: 6 * 60 * 1000,
    timeoutMessage: "Quá trình tạo sách ôn tập mất nhiều thời gian hơn dự kiến. Vui lòng thử làm mới lại sau.",
    defaultErrorMessage: "Tạo sách ôn tập thất bại.",
    onReady: () => setActiveIdx(-1),
  });

  const loading = isFetching || (!hasFetched && !error);

  const handleRefresh = async () => {
    setIsFetching(true);
    setError(null);
    try {
      const res = await apiGetBook(courseId);
      if (res.status === "ready" && res.data) {
        setBook(res.data);
        setActiveIdx(-1);
      } else if (res.status === "error") {
        setError(normalizePublicError(res.error_code, "Tạo sách ôn tập thất bại."));
      } else {
        setBook(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tải sách ôn tập.");
    } finally {
      setIsFetching(false);
    }
  };

  const handleGenerate = async () => {
    const retryVersionId = consumeJobRetryVersion();
    setGenerating(true);
    setError(null);
    setProgress(5);
    try {
      const res = await apiGenerateBook(courseId, {
        detail_level: detailLevel,
        user_prompt: userPrompt,
        ...(retryVersionId ? { retry_version_id: retryVersionId } : {}),
      });
      startJob(res.job_id, res.version_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bắt đầu tạo sách ôn tập thất bại.");
      setGenerating(false);
    }
  };

  // The backend persists a hard "error" status from the last generation attempt, so a plain
  // refetch would just surface the same error forever — retry opens the picker before a new job.
  const handleRetryAfterError = () => {
    clearJobRetryVersion();
    setRegenDialogOpen(true);
  };

  // Regenerating from the ready view keeps the current book visible (stale-while-revalidate)
  // instead of bouncing to the full-page ErrorState/EmptyState — a 429 (regen limit reached)
  // surfaces as a small inline banner instead of blowing away otherwise-valid content.
  const handleCreateVersion = async (retryVersionId: string | null = null) => {
    setRegenError(null);
    setGenerating(true);
    setProgress(5);
    try {
      const res = await apiGenerateBook(courseId, {
        detail_level: detailLevel,
        user_prompt: userPrompt,
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

  const optionValue = { detailLevel, userPrompt };
  const handleRenameVersion = async (versionId: string, label: string) => {
    try { await apiRenameArtifactVersion(courseId, "book", versionId, label); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể đổi tên phiên bản."); }
  };
  const handleDeleteVersion = async (versionId: string) => {
    if (!window.confirm("Xóa phiên bản này? Thao tác không thể hoàn tác.")) return;
    try { await apiDeleteArtifactVersion(courseId, "book", versionId); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể xóa phiên bản."); }
  };
  const updateOptions = (value: typeof optionValue) => {
    setDetailLevel(value.detailLevel);
    setUserPrompt(value.userPrompt);
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
          <DialogTitle>Tạo phiên bản sách mới</DialogTitle>
          <DialogDescription>
            Chọn cấu hình mới rồi xác nhận để bắt đầu tạo. Nội dung hiện tại vẫn được giữ cho đến khi bản mới sẵn sàng.
          </DialogDescription>
        </DialogHeader>
        <BookOptionsPanel
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
      onUpdate={(job) => setProgress(job.progress)}
      onSucceeded={resumeArtifactPolling}
      onTerminal={finishJob}
      onRetry={() => {
        prepareActiveJobRetry();
        setRegenDialogOpen(true);
      }}
    />
  ) : null;

  // ---------- Loading ----------
  if (loading) {
    return (
      <div className="space-y-6 py-6 animate-pulse">
        <Skeleton className="h-8 w-64 rounded-xl" />
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          <div className="lg:col-span-1 space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full rounded-xl" />
            ))}
          </div>
          <div className="lg:col-span-3 space-y-4">
            <Skeleton className="h-40 w-full rounded-2xl" />
            <Skeleton className="h-64 w-full rounded-2xl" />
          </div>
        </div>
      </div>
    );
  }

  // ---------- Error ----------
  if (error) {
    return (
      <>
        <ErrorState title="Lỗi tạo sách ôn tập" description={error} onRetry={handleRetryAfterError} retryLabel="Mở tùy chọn tạo mới" />
        {regenerateDialog}
      </>
    );
  }

  // ---------- Empty: config + generate ----------
  if (!book || !book.chapters || book.chapters.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="Chưa có sách ôn tập"
        description="Hệ thống sẽ tổng hợp tài liệu của bạn thành một cuốn sách ôn tập ngắn gọn, có mục lục và các chương rõ ràng để tự học hoặc giảng dạy."
        badge=""
      >
        {jobProgress ?? (
          <BookOptionsPanel
            value={optionValue}
            onChange={updateOptions}
            onSubmit={handleGenerate}
            busy={generating}
            progress={progress}
            submitLabel="Tạo sách ôn tập"
            documentProcessing={documentProcessing}
          />
        )}
      </EmptyState>
    );
  }

  // ---------- Reader ----------
  const chapters = book.chapters;
  const total = chapters.length;
  const activeChapter = activeIdx >= 0 ? chapters[activeIdx] : null;

  return (
    <div className="space-y-6 animate-in fade-in-50">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border bg-card/40 p-5 shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-3 min-w-0">
          <div className="rounded-xl bg-primary/10 p-2 text-primary shrink-0">
            <BookOpen className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight text-foreground truncate">
              <Markdown inline>{book.title}</Markdown>
            </h2>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary" className="font-medium">
                {total} chương
              </Badge>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <a
            href={getDownloadBookUrl(courseId, viewedVersion)}
            target="_blank"
            rel="noopener noreferrer"
            download
            className={buttonVariants({ variant: "outline", className: "gap-1.5" })}
          >
            <Download className="h-4 w-4" /> Tải PDF
          </a>
          {generating ? (
            <Button disabled variant="outline" className="gap-1.5">
              <RefreshCw className="h-4 w-4 animate-spin" /> Đang tạo ({progress}%)…
            </Button>
          ) : (
            <CreateVersionButton
              label="sách ôn tập"
              onOpen={openFreshVersionDialog}
            />
          )}
          <Button variant="outline" size="icon" onClick={handleRefresh} title="Tải lại sách" disabled={generating}>
            <RefreshCw className="h-4 w-4" />
          </Button>
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
        {/* Chapter rail */}
        {!isExpanded && (
          <div className="lg:col-span-1 space-y-3">
            <span className="flex items-center gap-1.5 px-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
              <ListChecks className="h-3.5 w-3.5" /> Mục lục
            </span>
            <div className="space-y-1.5">
              <button
                onClick={() => setActiveIdx(-1)}
                className={cn(
                  "block w-full rounded-lg border px-3 py-2 text-left text-sm font-medium transition-all",
                  activeIdx === -1
                    ? "border-primary bg-primary/10 text-primary ring-2 ring-primary/40"
                    : "border-border/60 bg-card text-muted-foreground hover:border-primary/40"
                )}
              >
                Giới thiệu
              </button>
              {chapters.map((ch, i) => (
                <button
                  key={i}
                  onClick={() => setActiveIdx(i)}
                  className={cn(
                    "block w-full rounded-lg border px-3 py-2 text-left text-sm font-medium transition-all",
                    activeIdx === i
                      ? "border-primary bg-primary/10 text-primary ring-2 ring-primary/40"
                      : "border-border/60 bg-card text-muted-foreground hover:border-primary/40"
                  )}
                >
                  <span className="mr-1.5 text-xs text-muted-foreground">{i + 1}.</span>
                  <Markdown inline>{ch.chapter_title}</Markdown>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Reading pane */}
        <div className={cn(isExpanded ? "lg:col-span-4" : "lg:col-span-3", "space-y-4")}>
          <div className="rounded-2xl border bg-card p-6 lg:p-8 shadow-[var(--shadow-sm)]">
            {activeChapter ? (
              <>
                <h3 className="text-2xl font-bold tracking-tight text-foreground">
                  Chương {activeIdx + 1}: <Markdown inline>{activeChapter.chapter_title}</Markdown>
                </h3>
                {activeChapter.introduction && (
                  <Markdown className="mt-4">{activeChapter.introduction}</Markdown>
                )}
                {activeChapter.objectives && activeChapter.objectives.length > 0 && (
                  <div className="mt-5 rounded-xl border border-primary/20 bg-primary/5 p-4">
                    <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-primary">
                      <Target className="h-3.5 w-3.5" /> Mục tiêu học tập
                    </p>
                    <ul className="space-y-1 text-sm text-foreground/90">
                      {activeChapter.objectives.map((obj, i) => (
                        <li key={i}>
                          ✔ <Markdown inline>{obj}</Markdown>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {activeChapter.sections.map((sec, i) => (
                  <div key={i} className="mt-6">
                    <h4 className="text-lg font-semibold text-foreground">
                      <Markdown inline>{sec.title}</Markdown>
                    </h4>
                    <Markdown className="mt-3">{sec.content}</Markdown>
                  </div>
                ))}

                {activeChapter.key_points && activeChapter.key_points.length > 0 && (
                  <div className="mt-6 rounded-xl border border-warning/30 bg-warning/5 p-4">
                    <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-warning">
                      <Star className="h-3.5 w-3.5" /> Điểm cốt lõi
                    </p>
                    <ul className="space-y-1 text-sm text-foreground/90">
                      {activeChapter.key_points.map((pt, i) => (
                        <li key={i}>
                          ★ <Markdown inline>{pt}</Markdown>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {activeChapter.review_questions && activeChapter.review_questions.length > 0 && (
                  <div className="mt-6 rounded-xl border bg-muted/40 p-4">
                    <p className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      <HelpCircle className="h-3.5 w-3.5" /> Câu hỏi ôn tập
                    </p>
                    <ol className="list-decimal space-y-1.5 pl-4 text-sm text-foreground/90">
                      {activeChapter.review_questions.map((q, i) => (
                        <li key={i}>
                          <Markdown inline>{q}</Markdown>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </>
            ) : (
              <>
                <h3 className="text-2xl font-bold tracking-tight text-foreground">
                  <Markdown inline>{book.title}</Markdown>
                </h3>
                {book.preface && <Markdown className="mt-4">{book.preface}</Markdown>}
                <div className="mt-6 rounded-xl border bg-muted/40 p-4">
                  <p className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Tóm tắt nội dung
                  </p>
                  <p className="text-sm leading-relaxed text-foreground/90">
                    <Markdown inline>{book.summary}</Markdown>
                  </p>
                </div>
              </>
            )}
          </div>

          {/* Nav bar */}
          <div className="flex items-center justify-between rounded-xl border bg-card/60 p-4 shadow-[var(--shadow-xs)]">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsExpanded((v) => !v)}
                className="gap-1.5 text-xs font-semibold"
              >
                {isExpanded ? "Hiện mục lục" : "Mở rộng"}
              </Button>
              <Button
                variant="outline"
                onClick={() => setActiveIdx((prev) => Math.max(-1, prev - 1))}
                disabled={activeIdx <= -1}
                className="gap-1 text-xs font-medium"
              >
                <ChevronLeft className="h-4 w-4" /> Trước
              </Button>
              <Button
                variant="outline"
                onClick={() => setActiveIdx((prev) => Math.min(total - 1, prev + 1))}
                disabled={activeIdx >= total - 1}
                className="gap-1 text-xs font-medium"
              >
                Sau <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
