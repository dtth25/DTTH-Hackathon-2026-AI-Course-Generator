"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleX, Clock3, Loader2, RotateCcw, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiRequestError, apiCancelJob, apiGetJob } from "@/lib/api";
import {
  normalizePublicError,
  type JobStatus,
  type JobStatusResponse,
  type JobType,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const JOB_POLL_MS = 3_000;
const REQUEST_TIMEOUT_MS = 10_000;
const ACTIVE_STATUSES: ReadonlySet<JobStatus> = new Set([
  "queued",
  "running",
  "retry_scheduled",
]);
const VIDEO_CANCEL_STATUSES: ReadonlySet<JobStatus> = new Set(["queued", "running"]);

const QUEUE_LABELS: Readonly<Record<JobType, string>> = {
  preprocess: "Hàng chờ xử lý tài liệu",
  book: "Hàng chờ tạo sách ôn tập",
  slides: "Hàng chờ tạo slide",
  quiz: "Hàng chờ tạo trắc nghiệm",
  video: "Hàng chờ dựng video",
};

const RUNNING_LABELS: Readonly<Record<JobType, string>> = {
  preprocess: "Đang xử lý tài liệu",
  book: "Đang tạo sách ôn tập",
  slides: "Đang tạo slide",
  quiz: "Đang tạo trắc nghiệm",
  video: "Đang dựng video",
};

interface JobProgressProps {
  jobId: string;
  allowCancel?: boolean;
  className?: string;
  onSucceeded?: () => void;
  onTerminal?: (status: Extract<JobStatus, "failed" | "cancelled">) => void;
  onRetry?: () => void;
  onUpdate?: (job: JobObservation) => void;
}

export type JobObservation = Pick<
  JobStatusResponse,
  "status" | "progress" | "updated_at" | "next_attempt_at" | "stage"
>;

function isAbortError(error: unknown): boolean {
  return Boolean(
    error && typeof error === "object" && "name" in error && error.name === "AbortError"
  );
}

function safeProgress(value: number): number {
  return Math.max(0, Math.min(100, Math.round(Number.isFinite(value) ? value : 0)));
}

function stageLabel(stage?: string): string {
  return ({
    queued: "Đang chờ",
    preprocessing: "Đang chuẩn bị tài liệu",
    extracting: "Đang đọc nội dung tài liệu",
    retrieving: "Đang lấy ngữ cảnh tài liệu",
    source_plan: "Đang lập kế hoạch nguồn",
    outline: "Đang lập dàn ý",
    chapter: "Đang viết chương",
    generating: "Đang tạo nội dung",
    rendering: "Đang dựng nội dung",
    exporting: "Đang xuất bản học liệu",
    processing: "Đang xử lý",
    capacity_wait: "Đang chờ lượt xử lý AI",
    waiting_to_retry: "Đang chờ thử lại",
    completed: "Đã hoàn tất",
    failed: "Không thành công",
    cancelled: "Đã hủy",
  } as Record<string, string>)[stage ?? "generating"] ?? "Đang xử lý";
}

export function JobProgress({
  jobId,
  allowCancel = false,
  className,
  onSucceeded,
  onTerminal,
  onRetry,
  onUpdate,
}: JobProgressProps) {
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [cancelPending, setCancelPending] = useState(false);
  const [pollError, setPollError] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestAbortRef = useRef<AbortController | null>(null);
  const cancelAbortRef = useRef<AbortController | null>(null);
  const terminalReportedRef = useRef(false);
  const onSucceededRef = useRef(onSucceeded);
  const onTerminalRef = useRef(onTerminal);
  const onUpdateRef = useRef(onUpdate);
  const generationRef = useRef(0);
  const requestRef = useRef(0);
  const stoppedRef = useRef(false);
  const inFlightRef = useRef(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    onSucceededRef.current = onSucceeded;
    onTerminalRef.current = onTerminal;
    onUpdateRef.current = onUpdate;
  });

  const clearTimers = useCallback(() => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
  }, []);

  useEffect(() => {
    terminalReportedRef.current = false;
    stoppedRef.current = false;
    inFlightRef.current = false;
    let mounted = true;
    const generation = ++generationRef.current;
    const startedAt = Date.now();
    const elapsedTimer = setInterval(() => {
      if (mounted) setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1_000);

    const scheduleNextPoll = (withJitter = false) => {
      if (!mounted || stoppedRef.current) return;
      clearTimers();
      const jitter = withJitter ? Math.floor(Math.random() * 2_001) : 0;
      pollTimerRef.current = setTimeout(() => {
        void poll();
      }, JOB_POLL_MS + jitter);
    };

    const poll = async () => {
      if (!mounted || stoppedRef.current || inFlightRef.current) return;
      clearTimers();
      inFlightRef.current = true;
      const request = ++requestRef.current;
      const controller = new AbortController();
      requestAbortRef.current = controller;
      const deadline = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
      try {
        const nextJob = await apiGetJob(jobId, { signal: controller.signal });
        if (!mounted || generationRef.current !== generation || requestRef.current !== request) return;
        setPollError(false);
        setJob(nextJob);
        onUpdateRef.current?.(nextJob);
        if (ACTIVE_STATUSES.has(nextJob.status)) {
          scheduleNextPoll();
          return;
        }
        stoppedRef.current = true;
        if (!terminalReportedRef.current) {
          terminalReportedRef.current = true;
          if (nextJob.status === "succeeded") onSucceededRef.current?.();
          if (nextJob.status === "failed" || nextJob.status === "cancelled") {
            onTerminalRef.current?.(nextJob.status);
          }
        }
      } catch (error) {
        if (!mounted || requestRef.current !== request || stoppedRef.current) return;
        if (isAbortError(error) && generationRef.current !== generation) return;
        setPollError(true);
        if (error instanceof ApiRequestError && (error.status === 401 || error.status === 403)) {
          stoppedRef.current = true;
          return;
        }
        scheduleNextPoll(true);
      } finally {
        clearTimeout(deadline);
        if (requestRef.current === request) inFlightRef.current = false;
        if (requestAbortRef.current === controller) requestAbortRef.current = null;
      }
    };

    void poll();
    const recheck = () => {
      if (!mounted || stoppedRef.current || document.visibilityState === "hidden") return;
      requestRef.current += 1;
      inFlightRef.current = false;
      requestAbortRef.current?.abort();
      void poll();
    };
    window.addEventListener("online", recheck);
    document.addEventListener("visibilitychange", recheck);
    return () => {
      mounted = false;
      stoppedRef.current = true;
      requestRef.current += 1;
      generationRef.current += 1;
      clearTimers();
      clearInterval(elapsedTimer);
      window.removeEventListener("online", recheck);
      document.removeEventListener("visibilitychange", recheck);
      requestAbortRef.current?.abort();
      requestAbortRef.current = null;
      cancelAbortRef.current?.abort();
      cancelAbortRef.current = null;
    };
  }, [clearTimers, jobId]);

  const requestCancellation = async () => {
    if (!job || job.job_type !== "video" || !VIDEO_CANCEL_STATUSES.has(job.status) || cancelPending) return;
    setCancelPending(true);
    const controller = new AbortController();
    cancelAbortRef.current = controller;
    try {
      const nextJob = await apiCancelJob(jobId, { signal: controller.signal });
      setCancelRequested(true);
      setJob(nextJob);
      if (!ACTIVE_STATUSES.has(nextJob.status)) {
        stoppedRef.current = true;
        requestRef.current += 1;
        inFlightRef.current = false;
        requestAbortRef.current?.abort();
        requestAbortRef.current = null;
        clearTimers();
        if (!terminalReportedRef.current && (nextJob.status === "failed" || nextJob.status === "cancelled")) {
          terminalReportedRef.current = true;
          onTerminalRef.current?.(nextJob.status);
        }
      }
    } catch (error) {
      if (!isAbortError(error)) setPollError(true);
    } finally {
      if (cancelAbortRef.current === controller) cancelAbortRef.current = null;
      setCancelPending(false);
    }
  };

  if (!job) {
    return (
      <div className={cn("rounded-xl border bg-card/50 px-4 py-4", className)} role="status">
        <span className="inline-flex items-center gap-2 text-sm font-medium">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang cập nhật tiến độ…
        </span>
      </div>
    );
  }

  const progress = safeProgress(job.progress);
  const queuePosition = job.queue_position && job.queue_position > 0
    ? ` · vị trí ${job.queue_position}`
    : "";
  const canCancel = allowCancel && job.job_type === "video" && VIDEO_CANCEL_STATUSES.has(job.status);
  const failedMessage = normalizePublicError(
    job.error_code,
    "Không thể hoàn tất tác vụ. Vui lòng thử lại."
  );
  const retryAt = job.next_attempt_at
    ? new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(job.next_attempt_at))
    : null;
  const isCapacityWait = job.stage === "capacity_wait";

  return (
    <div className={cn("space-y-3 rounded-xl border bg-card/50 px-4 py-4 shadow-[var(--shadow-xs)]", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {job.status === "queued" && (
            <>
              <p className="inline-flex items-center gap-2 font-medium"><Clock3 className="h-4 w-4" /> Đang chờ</p>
              <p className="mt-1 text-sm text-muted-foreground">{QUEUE_LABELS[job.job_type]}{queuePosition}</p>
            </>
          )}
          {job.status === "running" && (
            <>
              <p className="inline-flex items-center gap-2 font-medium">
                <Loader2 className="h-4 w-4 animate-spin" /> {RUNNING_LABELS[job.job_type]} ({progress}%)…
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{stageLabel(job.stage)} · đã chạy {elapsedSeconds} giây</p>
              {elapsedSeconds >= 360 && <p className="mt-1 text-sm text-muted-foreground">Tác vụ đang mất nhiều thời gian hơn dự kiến; hệ thống vẫn tiếp tục theo dõi.</p>}
            </>
          )}
          {job.status === "retry_scheduled" && (
            <>
              <p className="inline-flex items-center gap-2 font-medium"><RotateCcw className="h-4 w-4" /> {isCapacityWait ? stageLabel(job.stage) : "Đang chờ thử lại"}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {isCapacityWait
                  ? retryAt
                    ? `Hệ thống sẽ tự tiếp tục khi có lượt, dự kiến ${retryAt}`
                    : "Hệ thống sẽ tự tiếp tục khi có lượt xử lý AI"
                  : retryAt
                    ? `Dự kiến thử lại lúc ${retryAt}`
                    : "Đang chờ lịch thử lại từ máy chủ"}
              </p>
            </>
          )}
          {job.status === "cancelled" && (
            <p className="inline-flex items-center gap-2 font-medium"><X className="h-4 w-4" /> Đã hủy</p>
          )}
          {job.status === "failed" && (
            <>
              <p className="inline-flex items-center gap-2 font-medium text-error"><CircleX className="h-4 w-4" /> Tác vụ không thành công</p>
              <p role="alert" className="mt-1 text-sm text-muted-foreground">{failedMessage}</p>
            </>
          )}
          {job.status === "succeeded" && (
            <p className="inline-flex items-center gap-2 font-medium text-success"><CheckCircle2 className="h-4 w-4" /> Đã hoàn tất</p>
          )}
        </div>
        {canCancel && (
          <Button type="button" variant="outline" size="sm" disabled={cancelPending || cancelRequested} onClick={() => void requestCancellation()}>
            {cancelRequested ? "Đã yêu cầu hủy" : cancelPending ? "Đang gửi yêu cầu" : "Yêu cầu hủy"}
          </Button>
        )}
        {(job.status === "failed" || job.status === "cancelled") && onRetry && (
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            {job.status === "failed" ? "Thử lại" : "Tạo lại"}
          </Button>
        )}
      </div>

      {(job.status === "running" || job.status === "retry_scheduled") && (
        <div
          role="progressbar"
          aria-label="Tiến độ tác vụ"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
          className="h-2 overflow-hidden rounded-full bg-muted"
        >
          <div className="h-full bg-primary transition-[width] duration-[var(--duration-base)] ease-[var(--ease-standard)]" style={{ width: `${progress}%` }} />
        </div>
      )}

      {cancelRequested && (
        <p role="status" className="text-sm text-muted-foreground">
          Đã gửi yêu cầu hủy. Video sẽ dừng ở điểm an toàn gần nhất.
        </p>
      )}
      {pollError && (
        <p role="status" className="text-sm text-muted-foreground">
          Chưa thể cập nhật tiến độ. Hệ thống sẽ tự kết nối lại.
        </p>
      )}
    </div>
  );
}
