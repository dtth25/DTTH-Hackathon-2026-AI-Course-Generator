"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { toast } from "sonner";
import { usePollingArtifact } from "@/hooks/usePollingArtifact";
import {
  HelpCircle,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Download,
  ChevronLeft,
  ChevronRight,
  Trophy,
  RotateCcw,
  ListChecks,
  Lightbulb,
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
import { Markdown } from "@/components/ui/markdown";
import { cn } from "@/lib/utils";
import { QuizOptionsPanel } from "@/components/dashboard/QuizOptionsPanel";
import { CreateVersionButton } from "@/components/dashboard/CreateVersionButton";
import { VersionSwitcher } from "@/components/dashboard/VersionSwitcher";
import { JobProgress } from "@/components/dashboard/JobProgress";
import { ApiRequestError, apiDeleteArtifactVersion, apiGetQuiz, apiGenerateQuiz, apiRenameArtifactVersion, getDownloadQuizKeyUrl } from "@/lib/api";
import type { QuizQuestion } from "@/lib/types";

interface QuizTabProps {
  courseId: string;
  /** True while the course's document is still being extracted/indexed — generating now
   * would hit the backend's "still processing" guard, so the button is disabled instead. */
  documentProcessing?: boolean;
}

// --- Normalizers: quiz payload can vary in shape, keep the UI defensive ---
interface NormalizedOption {
  key: string;
  text: string;
}

function normalizeOptions(q: QuizQuestion): NormalizedOption[] {
  return (q.options || []).map((opt, i) => {
    const fallbackKey = String.fromCharCode(65 + i); // A, B, C, D
    if (typeof opt === "string") return { key: fallbackKey, text: opt };
    return { key: (opt.key || fallbackKey).toUpperCase(), text: opt.text ?? "" };
  });
}

function correctKeyOf(q: QuizQuestion): string {
  if (q.correct_answer) return String(q.correct_answer).trim().toUpperCase();
  if (typeof q.correct === "number") return String.fromCharCode(65 + q.correct);
  if (typeof q.correct === "string") return q.correct.trim().toUpperCase();
  return "A";
}

function questionTextOf(q: QuizQuestion, index: number): string {
  return q.question_text || q.question || `Câu hỏi ${index + 1}`;
}

// Map backend Bloom difficulty → Vietnamese label + badge variant
function difficultyMeta(raw?: string): { label: string; variant: "secondary" | "outline" | "destructive" } {
  const d = (raw || "").trim().toLowerCase();
  if (d === "easy") return { label: "Dễ", variant: "secondary" };
  if (d === "hard") return { label: "Khó", variant: "destructive" };
  if (d === "medium") return { label: "Vừa", variant: "outline" };
  return { label: raw || "Vừa", variant: "outline" };
}

export function QuizTab({ courseId, documentProcessing = false }: QuizTabProps) {
  // Generation config
  const [quantity, setQuantity] = useState(5);
  const [difficulty, setDifficulty] = useState("mixed");

  // Quiz-taking state (client-side, ephemeral)
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [showResults, setShowResults] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  const [regenDialogOpen, setRegenDialogOpen] = useState(false);

  const resetTaking = useCallback(() => {
    setCurrentIndex(0);
    setAnswers({});
    setShowResults(false);
  }, []);

  const {
    data: questions,
    setData: setQuestions,
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
  } = usePollingArtifact<QuizQuestion[]>({
    courseId,
    fetchFn: apiGetQuiz,
    isReady: (data) => data.length > 0,
    timeoutMs: 3 * 60 * 1000,
    timeoutMessage: "Quá trình tạo trắc nghiệm mất nhiều thời gian hơn dự kiến. Vui lòng thử lại sau.",
    defaultErrorMessage: "Tạo trắc nghiệm thất bại.",
    onReady: resetTaking,
  });

  const loading = !hasFetched && !error;

  const handleGenerate = async () => {
    const retryVersionId = consumeJobRetryVersion();
    setGenerating(true);
    setError(null);
    setProgress(5);
    try {
      const res = await apiGenerateQuiz(courseId, {
        quantity,
        difficulty,
        ...(retryVersionId ? { retry_version_id: retryVersionId } : {}),
      });
      startJob(res.job_id, res.version_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bắt đầu tạo trắc nghiệm thất bại.");
      setGenerating(false);
    }
  };

  // The backend persists a hard "error" status from the last generation attempt, so a plain
  // refetch would just surface the same error forever — retry opens the picker before a new job.
  const handleRetryAfterError = () => {
    clearJobRetryVersion();
    setRegenDialogOpen(true);
  };

  // Regenerating from the ready view keeps the current questions visible
  // (stale-while-revalidate) instead of bouncing to the full-page ErrorState/EmptyState —
  // a 429 (regen limit reached) surfaces as a small inline banner instead of blowing away
  // otherwise-valid content. Reuses the currently configured quantity/difficulty.
  const handleCreateVersion = async (retryVersionId: string | null = null) => {
    setRegenError(null);
    setGenerating(true);
    setProgress(5);
    try {
      const res = await apiGenerateQuiz(courseId, { quantity, difficulty, ...(retryVersionId ? { retry_version_id: retryVersionId } : {}) });
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

  const optionValue = { quantity, difficulty };
  const handleRenameVersion = async (versionId: string, label: string) => {
    try { await apiRenameArtifactVersion(courseId, "quiz", versionId, label); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể đổi tên phiên bản."); }
  };
  const handleDeleteVersion = async (versionId: string) => {
    if (!window.confirm("Xóa phiên bản này? Thao tác không thể hoàn tác.")) return;
    try { await apiDeleteArtifactVersion(courseId, "quiz", versionId); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể xóa phiên bản."); }
  };
  const updateOptions = (value: typeof optionValue) => {
    setQuantity(value.quantity);
    setDifficulty(value.difficulty);
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
          <DialogTitle>Tạo phiên bản câu hỏi mới</DialogTitle>
          <DialogDescription>
            Chọn cấu hình mới rồi xác nhận để bắt đầu tạo. Nội dung hiện tại vẫn được giữ cho đến khi bản mới sẵn sàng.
          </DialogDescription>
        </DialogHeader>
        <QuizOptionsPanel
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

  const total = questions?.length ?? 0;
  const currentQuestion = questions?.[currentIndex];

  const score = useMemo(() => {
    if (!questions) return 0;
    return questions.reduce((acc, q, i) => {
      const picked = answers[i];
      return acc + (picked && picked === correctKeyOf(q) ? 1 : 0);
    }, 0);
  }, [questions, answers]);

  const answeredCount = Object.keys(answers).length;
  const allAnswered = total > 0 && answeredCount === total;

  const handleSelect = (optionKey: string) => {
    if (!currentQuestion) return;
    if (answers[currentIndex] !== undefined) return; // locked once answered
    setAnswers((prev) => ({ ...prev, [currentIndex]: optionKey }));
  };

  // Keyboard navigation (mirrors SlideTab)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA"].includes((e.target as HTMLElement)?.tagName)) return;
      if (!questions || showResults) return;
      if (e.key === "ArrowLeft") {
        setCurrentIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === "ArrowRight") {
        setCurrentIndex((prev) => Math.min(questions.length - 1, prev + 1));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [questions, showResults]);

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
            <Skeleton className="h-12 w-full rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  // ---------- Error ----------
  if (error) {
    return (
      <>
        <ErrorState
          title="Lỗi tạo bộ câu hỏi"
          description={error}
          onRetry={handleRetryAfterError}
          retryLabel="Mở tùy chọn tạo mới"
        />
        {regenerateDialog}
      </>
    );
  }

  // ---------- Empty: config + generate ----------
  if (!questions || total === 0) {
    return (
      <EmptyState
        icon={HelpCircle}
        title="Chưa có bộ câu hỏi"
        description="Hệ thống sẽ phân tích tài liệu của bạn và tạo bộ câu hỏi trắc nghiệm bám sát nội dung để ôn luyện."
        badge=""
      >
        {jobProgress ?? (
          <QuizOptionsPanel
            value={optionValue}
            onChange={updateOptions}
            onSubmit={handleGenerate}
            busy={generating}
            progress={progress}
            submitLabel="Tạo trắc nghiệm"
            documentProcessing={documentProcessing}
          />
        )}
      </EmptyState>
    );
  }

  // ---------- Results ----------
  if (showResults) {
    const percent = total > 0 ? Math.round((score / total) * 100) : 0;
    const passed = percent >= 70;
    return (
      <div className="mx-auto max-w-2xl space-y-6 py-6 animate-in fade-in-50">
        {jobProgress}
        <div className="flex flex-col items-center gap-4 rounded-2xl border bg-card/40 p-8 text-center shadow-[var(--shadow-sm)]">
          <div
            className={cn(
              "rounded-2xl p-5",
              passed ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
            )}
          >
            <Trophy className="h-12 w-12" />
          </div>
          <div className="space-y-1">
            <h2 className="text-3xl font-bold text-foreground">
              {score}/{total} câu đúng
            </h2>
            <p className="text-sm text-muted-foreground">
              {passed
                ? `Bạn trả lời đúng ${percent}%. Xem lại phần giải thích trước khi làm lượt tiếp theo.`
                : `Bạn đạt ${percent}%. Hãy xem lại phần giải thích và luyện lại nhé.`}
            </p>
          </div>

          <div className="h-2.5 w-full max-w-sm overflow-hidden rounded-full bg-muted">
            <div
              className={cn("h-full rounded-full transition-all", passed ? "bg-success" : "bg-warning")}
              style={{ width: `${percent}%` }}
            />
          </div>

          <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
            <Button
              onClick={() => {
                resetTaking();
              }}
              className="gap-1.5 font-semibold"
            >
              <RotateCcw className="h-4 w-4" /> Làm lại
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setQuestions(null);
              }}
              className="gap-1.5"
            >
              <ListChecks className="h-4 w-4" /> Tạo bộ mới
            </Button>
            <a
              href={getDownloadQuizKeyUrl(courseId, viewedVersion)}
              target="_blank"
              rel="noopener noreferrer"
              download
              className={buttonVariants({ variant: "outline", className: "gap-1.5" })}
            >
              <Download className="h-4 w-4" /> Đáp án PDF
            </a>
          </div>
        </div>

        {/* Per-question review */}
        <div className="space-y-3">
          {questions.map((q, i) => {
            const opts = normalizeOptions(q);
            const correct = correctKeyOf(q);
            const picked = answers[i];
            const isCorrect = picked === correct;
            return (
              <div
                key={i}
                className={cn(
                  "rounded-xl border p-4 text-sm shadow-[var(--shadow-xs)]",
                  isCorrect ? "border-success/40 bg-success/5" : "border-error/40 bg-error/5"
                )}
              >
                <div className="flex items-start gap-2">
                  {isCorrect ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  ) : (
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-error" />
                  )}
                  <div className="space-y-1">
                    <p className="font-semibold text-foreground">
                      Câu {i + 1}. <Markdown inline>{questionTextOf(q, i)}</Markdown>
                    </p>
                    <p className="text-muted-foreground">
                      Đáp án đúng:{" "}
                      <span className="font-semibold text-success">
                        {correct}. <Markdown inline>{opts.find((o) => o.key === correct)?.text}</Markdown>
                      </span>
                    </p>
                    {!isCorrect && picked && (
                      <p className="text-muted-foreground">
                        Bạn chọn:{" "}
                        <span className="font-semibold text-error">
                          {picked}. <Markdown inline>{opts.find((o) => o.key === picked)?.text}</Markdown>
                        </span>
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // ---------- Taking the quiz ----------
  const opts = currentQuestion ? normalizeOptions(currentQuestion) : [];
  const correct = currentQuestion ? correctKeyOf(currentQuestion) : "";
  const picked = answers[currentIndex];
  const isAnswered = picked !== undefined;
  const diffMeta = difficultyMeta(currentQuestion?.difficulty);

  return (
    <div className="space-y-6 animate-in fade-in-50">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border bg-card/40 p-5 shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-3 min-w-0">
          <div className="rounded-xl bg-primary/10 p-2 text-primary shrink-0">
            <HelpCircle className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight text-foreground">
              Bộ câu hỏi trắc nghiệm
            </h2>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary" className="font-medium">
                {total} câu
              </Badge>
              <span>Đã làm {answeredCount}/{total}</span>
              <span className="text-success font-semibold">· {score} đúng</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <a
            href={getDownloadQuizKeyUrl(courseId, viewedVersion)}
            target="_blank"
            rel="noopener noreferrer"
            download
            className={buttonVariants({ variant: "outline", className: "gap-1.5" })}
          >
            <Download className="h-4 w-4" /> Đáp án PDF
          </a>
          {allAnswered && (
            <Button onClick={() => setShowResults(true)} className="gap-1.5 font-semibold">
              <Trophy className="h-4 w-4" /> Xem kết quả
            </Button>
          )}
          {generating ? (
            <Button disabled variant="outline" className="gap-1.5">
              <RefreshCw className="h-4 w-4 animate-spin" /> Đang tạo lại ({progress}%)…
            </Button>
          ) : (
            <CreateVersionButton
              label="bộ câu hỏi"
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

      {/* Progress bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${total > 0 ? ((currentIndex + 1) / total) * 100 : 0}%` }}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Question rail */}
        <div className="lg:col-span-1 space-y-3">
          <span className="flex items-center gap-1.5 px-1 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <ListChecks className="h-3.5 w-3.5" /> Danh sách câu ({total})
          </span>
          <div className="grid grid-cols-5 gap-2 lg:grid-cols-4">
            {questions.map((q, i) => {
              const a = answers[i];
              const state =
                a === undefined ? "todo" : a === correctKeyOf(q) ? "correct" : "wrong";
              return (
                <button
                  key={i}
                  onClick={() => setCurrentIndex(i)}
                  className={cn(
                    "flex h-9 items-center justify-center rounded-lg border text-sm font-semibold transition-all",
                    i === currentIndex && "ring-2 ring-primary/40",
                    state === "todo" &&
                      "border-border/60 bg-card text-muted-foreground hover:border-primary/40",
                    state === "correct" && "border-success/50 bg-success/10 text-success",
                    state === "wrong" && "border-error/50 bg-error/10 text-error"
                  )}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
        </div>

        {/* Question card */}
        <div className="lg:col-span-3 space-y-4">
          <div className="rounded-2xl border bg-card p-6 shadow-[var(--shadow-sm)]">
            <div className="mb-4 flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-muted-foreground">
                Câu {currentIndex + 1} / {total}
              </span>
              <Badge variant={diffMeta.variant} className="font-medium">
                {diffMeta.label}
              </Badge>
            </div>

            <p className="mb-5 text-lg font-semibold leading-relaxed text-foreground">
              <Markdown inline>
                {currentQuestion ? questionTextOf(currentQuestion, currentIndex) : ""}
              </Markdown>
            </p>

            <div className="space-y-2.5">
              {opts.map((opt) => {
                const isCorrectOpt = opt.key === correct;
                const isPickedOpt = opt.key === picked;
                let tone =
                  "border-border/70 bg-card hover:border-primary/50 hover:bg-primary/5";
                if (isAnswered) {
                  if (isCorrectOpt)
                    tone = "border-success/60 bg-success/10 text-success";
                  else if (isPickedOpt)
                    tone = "border-error/60 bg-error/10 text-error";
                  else tone = "border-border/50 bg-card opacity-60";
                }
                return (
                  <button
                    key={opt.key}
                    onClick={() => handleSelect(opt.key)}
                    disabled={isAnswered}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl border p-3.5 text-left text-sm font-medium transition-all",
                      tone,
                      !isAnswered && "cursor-pointer"
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-xs font-bold",
                        isAnswered && isCorrectOpt && "border-success bg-success text-success-foreground",
                        isAnswered && isPickedOpt && !isCorrectOpt && "border-error bg-error text-error-foreground",
                        !(isAnswered && (isCorrectOpt || isPickedOpt)) && "border-border/70 bg-muted text-foreground"
                      )}
                    >
                      {opt.key}
                    </span>
                    <span className="flex-1 text-foreground">
                      <Markdown inline>{opt.text}</Markdown>
                    </span>
                    {isAnswered && isCorrectOpt && (
                      <CheckCircle2 className="h-5 w-5 shrink-0 text-success" />
                    )}
                    {isAnswered && isPickedOpt && !isCorrectOpt && (
                      <XCircle className="h-5 w-5 shrink-0 text-error" />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Explanation (immediate feedback) */}
            {isAnswered && currentQuestion?.explanation && (
              <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 p-4 animate-in fade-in-50">
                <p className="mb-1 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-primary">
                  <Lightbulb className="h-3.5 w-3.5" /> Giải thích
                </p>
                <p className="text-sm leading-relaxed text-foreground/90">
                  <Markdown inline>{currentQuestion.explanation}</Markdown>
                </p>
              </div>
            )}
          </div>

          {/* Nav bar */}
          <div className="flex items-center justify-between rounded-xl border bg-card/60 p-4 shadow-[var(--shadow-xs)]">
            <Button
              variant="outline"
              onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
              disabled={currentIndex === 0}
              className="gap-1 text-xs font-medium"
            >
              <ChevronLeft className="h-4 w-4" /> Câu trước
            </Button>
            {currentIndex === total - 1 ? (
              <Button
                onClick={() => setShowResults(true)}
                disabled={!isAnswered}
                className="gap-1 text-xs font-semibold"
              >
                <Trophy className="h-4 w-4" /> Xem kết quả
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={() => setCurrentIndex((prev) => Math.min(total - 1, prev + 1))}
                className="gap-1 text-xs font-medium"
              >
                Câu tiếp <ChevronRight className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
