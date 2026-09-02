"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, FolderOpen, AlertCircle, RefreshCw } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { CourseCard } from "@/components/course/CourseCard";
import { apiGetCourses } from "@/lib/api";
import type { CourseListItem } from "@/lib/types";
import { CONTAINER_WIDE } from "@/lib/layout";
import { cn } from "@/lib/utils";
import { DEFAULT_POLL_MS } from "@/hooks/usePollingArtifact";

export default function CoursesPage() {
  return (
    <AuthGuard>
      <CoursesContent />
    </AuthGuard>
  );
}

function CoursesContent() {
  const [courses, setCourses] = useState<CourseListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCourses = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiGetCourses();
      setCourses(res.courses || []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Không thể tải danh sách khóa học."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    apiGetCourses()
      .then((res) => {
        if (active) {
          setCourses(res.courses || []);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Không thể tải danh sách khóa học."
          );
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const hasProcessing = courses.some(c => c.status === "processing");
    if (!hasProcessing) return;

    const interval = setInterval(async () => {
      try {
        const res = await apiGetCourses();
        setCourses(res.courses || []);
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, DEFAULT_POLL_MS);

    return () => clearInterval(interval);
  }, [courses]);

  return (
    <div
      data-visual-state={
        !loading && !error
          ? courses.length === 0
            ? "courses-empty"
            : "courses-populated"
          : undefined
      }
      className={cn(CONTAINER_WIDE, "py-8 sm:py-12")}
    >
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-semibold text-foreground sm:text-4xl">
            Khóa học của tôi
          </h1>
          <p className="mt-1 text-muted-foreground">
            Quản lý và truy cập các khóa học đã tạo
          </p>
        </div>
        <Link href="/courses/create" className={buttonVariants()}>
          <Plus className="mr-2 h-4 w-4" />
          Tạo mới
        </Link>
      </div>

      {loading && (
        <div
          role="status"
          aria-label="Đang tải khóa học"
          className="grid items-start gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3"
        >
          {[1, 2, 3].map((i) => (
            <div key={i} className="space-y-3 border-y border-t-[3px] p-6">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-1/3" />
              <div className="flex gap-2 pt-2">
                <Skeleton className="h-9 flex-1" />
                <Skeleton className="h-9 w-9" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="max-w-xl border-t-[3px] border-destructive py-8">
          <AlertCircle className="mb-4 h-8 w-8 text-destructive" />
          <h3 className="text-lg font-semibold text-foreground">
            Không tải được danh sách khóa học
          </h3>
          <p className="mt-2 max-w-md text-muted-foreground">{error}</p>
          <Button className="mt-6" onClick={fetchCourses}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Thử lại
          </Button>
        </div>
      )}

      {!loading && !error && courses.length === 0 && (
        <div className="max-w-xl border-t-[3px] border-[var(--accent-strong)] py-10">
          <FolderOpen className="mb-5 h-9 w-9 text-primary" />
          <h3 className="font-display text-2xl font-semibold text-foreground">
            Chưa có khóa học nào
          </h3>
          <p className="mt-2 text-muted-foreground max-w-md">
            Tải tệp đầu tiên để mở một không gian học mới.
          </p>
          <Link
            href="/courses/create"
            className={buttonVariants({ className: "mt-6" })}
          >
            <Plus className="mr-2 h-4 w-4" />
            Tạo khóa học đầu tiên
          </Link>
        </div>
      )}

      {!loading && !error && courses.length > 0 && (
        <div className="grid items-start gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((course) => (
            <CourseCard
              key={course.course_id}
              course={course}
              onDeleted={fetchCourses}
              onRenamed={fetchCourses}
            />
          ))}
        </div>
      )}
    </div>
  );
}
