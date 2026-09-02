"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  AlertCircle,
  Loader2,
  CheckCircle2,
  RefreshCw,
  BookOpen,
  Presentation,
  HelpCircle,
  Video,
  FileUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorState } from "@/components/ui/error-state";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { BookTab } from "@/components/dashboard/BookTab";
import { SlideTab } from "@/components/dashboard/SlideTab";
import { QuizTab } from "@/components/dashboard/QuizTab";
import { VidTab } from "@/components/dashboard/VidTab";
import { QualityScoreBadge } from "@/components/ui/QualityScoreBadge";
import {
  apiGetCourseStatus,
  apiGetStudyPack,
  apiRetryDocument,
  ApiNetworkError,
  ApiRequestError,
  NETWORK_UNAVAILABLE_MESSAGE,
} from "@/lib/api";
import type { CourseStatusResponse, StudyPackResponse } from "@/lib/types";
import {
  normalizeCourseStatus,
  normalizeDocumentRecommendedAction,
} from "@/lib/types";
import { CONTAINER_NARROW } from "@/lib/layout";
import { cn } from "@/lib/utils";
import { DEFAULT_POLL_MS } from "@/hooks/usePollingArtifact";

export default function CourseDashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  );
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "AbortError"
  );
}

function asError(error: unknown, fallback: string): Error {
  return error instanceof Error ? error : new Error(fallback);
}

function DashboardContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [course, setCourse] = useState<CourseStatusResponse | null>(null);
  const [studyPack, setStudyPack] = useState<StudyPackResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<Error | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestAbortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);

  const isCurrentGeneration = useCallback((generation: number) =>
    generationRef.current === generation, []);

  const cancelActiveWork = useCallback(() => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    requestAbortRef.current?.abort();
    requestAbortRef.current = null;
  }, []);

  const beginGeneration = useCallback(() => {
    cancelActiveWork();
    generationRef.current += 1;
    return generationRef.current;
  }, [cancelActiveWork]);

  const fetchCourseSnapshot = useCallback(async (courseId: string, generation: number) => {
    const controller = new AbortController();
    requestAbortRef.current = controller;
    try {
      const [statusData, packData] = await Promise.all([
        apiGetCourseStatus(courseId, { signal: controller.signal }),
        apiGetStudyPack(courseId, { signal: controller.signal }).catch((error) => {
          if (isAbortError(error)) throw error;
          return null;
        }),
      ]);
      return isCurrentGeneration(generation) ? { statusData, packData } : null;
    } finally {
      if (requestAbortRef.current === controller) requestAbortRef.current = null;
    }
  }, [isCurrentGeneration]);

  const schedulePolling = useCallback((courseId: string, generation: number) => {
    const poll = async () => {
      if (!isCurrentGeneration(generation)) return;
      try {
        const snapshot = await fetchCourseSnapshot(courseId, generation);
        if (!snapshot || !isCurrentGeneration(generation)) return;
        setCourse(snapshot.statusData);
        setStudyPack(snapshot.packData);
        if (normalizeCourseStatus(snapshot.statusData.status) !== "processing") return;
      } catch (error) {
        if (!isCurrentGeneration(generation) || isAbortError(error)) return;
      }
      if (isCurrentGeneration(generation)) {
        pollTimerRef.current = setTimeout(poll, DEFAULT_POLL_MS);
      }
    };
    pollTimerRef.current = setTimeout(poll, DEFAULT_POLL_MS);
  }, [fetchCourseSnapshot, isCurrentGeneration]);

  const loadCourse = useCallback(async (courseId: string, generation: number, showLoading: boolean) => {
    if (showLoading) {
      setLoading(true);
      setPageError(null);
    }
    try {
      const snapshot = await fetchCourseSnapshot(courseId, generation);
      if (!snapshot || !isCurrentGeneration(generation)) return;
      setCourse(snapshot.statusData);
      setStudyPack(snapshot.packData);
      if (normalizeCourseStatus(snapshot.statusData.status) === "processing") {
        schedulePolling(courseId, generation);
      }
    } catch (error) {
      if (isCurrentGeneration(generation) && !isAbortError(error)) {
        setPageError(asError(error, "Không thể tải thông tin khóa học."));
      }
    } finally {
      if (showLoading && isCurrentGeneration(generation)) setLoading(false);
    }
  }, [fetchCourseSnapshot, isCurrentGeneration, schedulePolling]);

  const handleRefetch = useCallback(() => {
    if (!params.id) return;
    const generation = beginGeneration();
    void loadCourse(params.id, generation, true);
  }, [beginGeneration, loadCourse, params.id]);

  useEffect(() => {
    if (!params.id) return;
    const generation = beginGeneration();
    void loadCourse(params.id, generation, true);
    return () => {
      if (isCurrentGeneration(generation)) beginGeneration();
    };
  }, [beginGeneration, isCurrentGeneration, loadCourse, params.id]);

  const handleDocumentRetry = useCallback(async () => {
    if (!course || retrying) return;
    const generation = beginGeneration();
    const controller = new AbortController();
    requestAbortRef.current = controller;
    setRetrying(true);
    setRetryError(null);
    try {
      await apiRetryDocument(course.course_id, { signal: controller.signal });
      if (!isCurrentGeneration(generation)) return;
      void loadCourse(course.course_id, generation, true);
    } catch (error) {
      if (isCurrentGeneration(generation) && !isAbortError(error)) {
        setRetryError(asError(error, "Không thể thử lại tài liệu.").message);
      }
    } finally {
      if (requestAbortRef.current === controller) requestAbortRef.current = null;
      if (isCurrentGeneration(generation)) setRetrying(false);
    }
  }, [beginGeneration, course, isCurrentGeneration, loadCourse, retrying]);

  if (loading) {
    return (
      <div className={cn(CONTAINER_NARROW, "py-8 sm:py-12 space-y-6")}>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-12 w-full mt-4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (pageError) {
    const isNetworkError = pageError instanceof ApiNetworkError;
    const isMissingCourse = pageError instanceof ApiRequestError && pageError.status === 404;
    const title = isNetworkError
      ? "Không thể kết nối đến máy chủ"
      : isMissingCourse
        ? "Không tìm thấy khóa học"
        : "Không thể tải khóa học";
    return (
      <div className={cn(CONTAINER_NARROW, "py-16 text-center")}>
        <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-foreground">
          {title}
        </h2>
        <p className="mt-2 text-muted-foreground max-w-md mx-auto">
          {pageError.message}
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Button
            variant="outline"
            onClick={() => router.push("/courses")}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Quay lại
          </Button>
          <Button variant="outline" onClick={handleRefetch}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {isNetworkError ? "Thử kết nối lại" : "Thử lại"}
          </Button>
        </div>
      </div>
    );
  }

  if (!course) return null;

  const status = normalizeCourseStatus(course.status);
  const statusConfig = {
    processing: {
      label: "Đang xử lý",
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
      className: "border-warning text-warning",
    },
    ready: {
      label: "Sẵn sàng",
      icon: <CheckCircle2 className="h-3 w-3" />,
      className: "border-success text-success",
    },
    error: {
      label: "Lỗi",
      icon: <AlertCircle className="h-3 w-3" />,
      className: "",
    },
  };
  const cfg = statusConfig[status];
  const isNetworkUnavailable = course.error_code === "NETWORK_UNAVAILABLE";
  const failureMessage = isNetworkUnavailable
    ? NETWORK_UNAVAILABLE_MESSAGE
    : course.error || "Xử lý tài liệu thất bại.";
  const recommendedAction = normalizeDocumentRecommendedAction(course.recommended_action);
  const canRetryDocument = Boolean(
    isNetworkUnavailable ||
      (course.can_retry &&
        (recommendedAction === "restore_provider_quota" || recommendedAction === "retry_later"))
  );
  const displayTitle =
    course.name ||
    course.filenames?.[0] ||
    course.filename ||
    `Khóa học ${course.course_id.slice(0, 8)}`;

  return (
    <div
      data-visual-state="course-workspace"
      className={cn(CONTAINER_NARROW, "py-8 sm:py-12")}
    >
      {/* Course Header */}
      <header className="mb-8 border-b pb-6">
        <Button
          variant="ghost"
          size="sm"
          className="mb-4 -ml-2 text-muted-foreground"
          onClick={() => router.push("/courses")}
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Khóa học của tôi
        </Button>

        <div>
          <div>
            <h1 className="font-display text-3xl font-semibold text-foreground sm:text-4xl">
              {displayTitle}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {course.filenames && course.filenames.length > 0 && (
                <span className="flex items-center gap-1">
                  <FileText className="h-3.5 w-3.5" />
                  {course.filenames.length} tệp nguồn
                </span>
              )}
              <Badge
                variant="outline"
                className={`gap-1 ${cfg.className}`}
              >
                {cfg.icon}
                {cfg.label}
              </Badge>
              {course.quality_score !== undefined && course.quality_score > 0 ? (
                <QualityScoreBadge score={course.quality_score} />
              ) : studyPack?.study_pack?.grounding?.quality_score ? (
                <QualityScoreBadge
                  score={studyPack.study_pack.grounding.quality_score}
                />
              ) : null}
            </div>
          </div>
        </div>
      </header>

      {status === "error" ? (
        <ErrorState
          className="my-0"
          title="Không thể xử lý tài liệu"
          description={
            <>
              <span>{failureMessage}</span>
              {recommendedAction === "restore_provider_quota" && (
                <span className="mt-2 block">
                  Tệp đã tải lên vẫn được giữ nguyên. Quản trị viên cần khôi phục dung lượng AI trước khi bạn thử lại.
                </span>
              )}
              {recommendedAction === "retry_later" && (
                <span className="mt-2 block">
                  Tệp đã tải lên vẫn được giữ nguyên và có thể được lập chỉ mục lại sau ít phút.
                </span>
              )}
              {recommendedAction === "upload_clearer_pdf" && (
                <span className="mt-2 block">
                  Thử lại cùng tệp này sẽ không giúp. Hãy tải tệp rõ hơn hoặc thay tệp nguồn.
                </span>
              )}
              {retryError && <span role="alert" className="mt-2 block text-error">{retryError}</span>}
            </>
          }
          onAction={
            recommendedAction === "upload_clearer_pdf"
              ? () => router.push(`/courses/create?replace=${encodeURIComponent(course.course_id)}`)
              : canRetryDocument
                ? handleDocumentRetry
                : undefined
          }
          actionLabel={
            recommendedAction === "upload_clearer_pdf"
              ? "Tải tệp thay thế"
              : retrying
                ? "Đang thử lại"
                : "Thử lập chỉ mục lại"
          }
          actionDisabled={retrying}
          actionIcon={
            recommendedAction === "upload_clearer_pdf"
              ? <FileUp className="h-4 w-4" />
              : retrying
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <RefreshCw className="h-4 w-4" />
          }
        />
      ) : (
      <Tabs defaultValue="book" className="w-full">
        <TabsList
          variant="line"
          aria-label="Loại học liệu"
          className="h-auto w-full justify-start gap-1 overflow-x-auto border-y py-2"
        >
          <TabsTrigger value="book" className="flex-none gap-1.5">
            <BookOpen className="h-4 w-4" /> Study Guide
          </TabsTrigger>
          <TabsTrigger value="slide" className="flex-none gap-1.5">
            <Presentation className="h-4 w-4" /> Slide
          </TabsTrigger>
          <TabsTrigger value="quiz" className="flex-none gap-1.5">
            <HelpCircle className="h-4 w-4" /> Quiz
          </TabsTrigger>
          <TabsTrigger value="vid" className="flex-none gap-1.5">
            <Video className="h-4 w-4" /> Video
          </TabsTrigger>
        </TabsList>

        <section
          aria-label="Học liệu của khóa học"
          className="mt-6 min-h-[400px] border-t-[3px] border-[var(--accent-strong)] px-0 py-6 sm:px-4 sm:py-8"
        >
          <TabsContent value="book" className="mt-0">
            <BookTab courseId={course.course_id} documentProcessing={status === "processing"} />
          </TabsContent>
          <TabsContent value="slide" className="mt-0">
            <SlideTab courseId={course.course_id} documentProcessing={status === "processing"} />
          </TabsContent>
          <TabsContent value="quiz" className="mt-0">
            <QuizTab courseId={course.course_id} documentProcessing={status === "processing"} />
          </TabsContent>
          <TabsContent value="vid" className="mt-0">
            <VidTab courseId={course.course_id} documentProcessing={status === "processing"} />
          </TabsContent>
        </section>
      </Tabs>
      )}
    </div>
  );
}
