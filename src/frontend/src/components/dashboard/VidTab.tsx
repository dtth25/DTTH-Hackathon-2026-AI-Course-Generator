"use client";

import { useState } from "react";
import { toast } from "sonner";
import { usePollingArtifact } from "@/hooks/usePollingArtifact";
import {
  Video,
  RefreshCw,
  Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { VidOptionsPanel } from "@/components/dashboard/VidOptionsPanel";
import { CreateVersionButton } from "@/components/dashboard/CreateVersionButton";
import { VersionSwitcher } from "@/components/dashboard/VersionSwitcher";
import { JobProgress } from "@/components/dashboard/JobProgress";
import {
  ApiRequestError,
  apiDeleteArtifactVersion,
  apiGetVid,
  apiGenerateVid,
  apiRenameArtifactVersion,
  getDownloadVidMp4Url,
} from "@/lib/api";
import type { VidOutput } from "@/lib/types";

interface VidTabProps {
  courseId: string;
  /** True while the course's document is still being extracted/indexed — generating now
   * would hit the backend's "still processing" guard, so the button is disabled instead. */
  documentProcessing?: boolean;
}

function formatDuration(totalSeconds?: number | null): string {
  const s = Math.max(0, Math.round(totalSeconds || 0));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export function VidTab({ courseId, documentProcessing = false }: VidTabProps) {
  // Generation config
  const [format, setFormat] = useState("standard");
  const [voice, setVoice] = useState("female");
  const [userPrompt, setUserPrompt] = useState("");
  const [regenError, setRegenError] = useState<string | null>(null);
  const [regenDialogOpen, setRegenDialogOpen] = useState(false);


  const {
    data: video,
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
  } = usePollingArtifact<VidOutput>({
    courseId,
    fetchFn: apiGetVid,
    isReady: (data) => (data.scenes?.length ?? 0) > 0,
    timeoutMs: 8 * 60 * 1000,
    timeoutMessage: "Quá trình tạo video mất nhiều thời gian hơn dự kiến. Vui lòng thử lại sau.",
    defaultErrorMessage: "Tạo video thất bại.",
  });

  const loading = !hasFetched && !error;



  const handleGenerate = async () => {
    const retryVersionId = consumeJobRetryVersion();
    setGenerating(true);
    setError(null);
    setProgress(5);
    try {
      const res = await apiGenerateVid(courseId, {
        format,
        voice,
        user_prompt: userPrompt,
        ...(retryVersionId ? { retry_version_id: retryVersionId } : {}),
      });
      startJob(res.job_id, res.version_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bắt đầu tạo video thất bại.");
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
    try { await apiRenameArtifactVersion(courseId, "vid", versionId, label); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể đổi tên phiên bản."); }
  };
  const handleDeleteVersion = async (versionId: string) => {
    if (!window.confirm("Xóa phiên bản này? Thao tác không thể hoàn tác.")) return;
    try { await apiDeleteArtifactVersion(courseId, "vid", versionId); refresh(); }
    catch (err) { setRegenError(err instanceof Error ? err.message : "Không thể xóa phiên bản."); }
  };

  // Regenerating from the ready view keeps the current video visible (stale-while-revalidate)
  // instead of bouncing to the full-page ErrorState/EmptyState — a 429 (regen limit reached)
  // surfaces as a small inline banner instead of blowing away otherwise-valid content.
  const handleCreateVersion = async (retryVersionId: string | null = null) => {
    setRegenError(null);
    setGenerating(true);
    setProgress(5);
    try {
      const res = await apiGenerateVid(courseId, { format, voice, user_prompt: userPrompt, ...(retryVersionId ? { retry_version_id: retryVersionId } : {}) });
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

  const optionValue = { format, voice, userPrompt };
  const updateOptions = (value: typeof optionValue) => {
    setFormat(value.format);
    setVoice(value.voice);
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
          <DialogTitle>Tạo phiên bản video mới</DialogTitle>
          <DialogDescription>
            Chọn cấu hình mới rồi xác nhận để bắt đầu tạo. Nội dung hiện tại vẫn được giữ cho đến khi bản mới sẵn sàng.
          </DialogDescription>
        </DialogHeader>
        <VidOptionsPanel
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
      allowCancel
      onSucceeded={resumeArtifactPolling}
      onTerminal={finishJob}
      onRetry={() => {
        prepareActiveJobRetry();
        setRegenDialogOpen(true);
      }}
    />
  ) : null;


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
        <Skeleton className="aspect-video w-full rounded-2xl" />
      </div>
    );
  }

  if (error) {
    return (
      <>
        <ErrorState
          title="Lỗi tạo video"
          description={error}
          onRetry={handleRetryAfterError}
          retryLabel="Mở tùy chọn tạo mới"
        />
        {regenerateDialog}
      </>
    );
  }

  if (!video || !video.scenes || video.scenes.length === 0) {
    return (
      <EmptyState
        icon={Video}
        title="Chưa có video bài giảng"
        description="Hệ thống sẽ dựng một video ngắn có giọng đọc Tiếng Việt, tóm tắt và trình bày nội dung tài liệu của bạn theo từng phần."
        badge=""
      >
        {jobProgress ?? (
          <VidOptionsPanel
            value={optionValue}
            onChange={updateOptions}
            onSubmit={handleGenerate}
            busy={generating}
            progress={progress}
            submitLabel="Tạo video bài giảng"
            documentProcessing={documentProcessing}
          />
        )}
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in-50">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card/40 p-5 rounded-2xl border shadow-[var(--shadow-xs)]">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 rounded-xl bg-primary/10 text-primary shrink-0">
            <Video className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-semibold text-foreground tracking-tight truncate">
              {video.title || "Video bài giảng"}
            </h2>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary" className="font-medium">
                {video.scenes.length} cảnh
              </Badge>
              <span>{formatDuration(video.total_duration_seconds)}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <a href={getDownloadVidMp4Url(courseId, viewedVersion)} target="_blank" rel="noopener noreferrer" download className="inline-flex h-10 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Download className="h-4 w-4" /> Tải MP4
          </a>

          {generating ? (
            <Button disabled variant="outline" className="gap-1.5">
              <RefreshCw className="h-4 w-4 animate-spin" /> Đang tạo ({progress}%)…
            </Button>
          ) : (
            <CreateVersionButton
              label="video"
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

      {/* Player stage */}
      <div
        className="w-full bg-stage border border-stage-border rounded-2xl shadow-2xl relative overflow-hidden text-stage-foreground flex items-center justify-center p-2 sm:p-4"
      >
        <video
          key={courseId}
          controls
          className={cn(
            "max-w-full rounded-lg max-h-[70vh]"
          )}
          src={getDownloadVidMp4Url(courseId, viewedVersion)}
        />
      </div>
    </div>
  );
}
