"use client"

import { BookText, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import { ChapterAccordion } from "./ChapterAccordion"
import { useCourse } from "@/hooks/useCourse"

interface CourseViewProps {
  fileId: string
}

export function CourseView({ fileId }: CourseViewProps) {
  const { course, loading, error } = useCourse(fileId)

  // Loading state: Skeleton UI
  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <div className="space-y-3 mt-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-20 w-full ml-4" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4" />
          Lỗi tải khóa học
        </AlertTitle>
        <AlertDescription>
          {error}
        </AlertDescription>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => window.location.reload()}
        >
          Thử lại
        </Button>
      </Alert>
    )
  }

  // Empty / no data state
  if (!course) {
    return (
      <Alert>
        <AlertTitle>Chưa có dữ liệu</AlertTitle>
        <AlertDescription>
          Không tìm thấy khóa học. Vui lòng upload tài liệu trước.
        </AlertDescription>
      </Alert>
    )
  }

  // Success state
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 pb-2 border-b">
        <BookText className="h-6 w-6 text-blue-500" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Khóa học: {course.course_title}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {course.chapters.length} chương,{" "}
            {course.chapters.reduce((sum, ch) => sum + ch.lessons.length, 0)}{" "}
            bài học
          </p>
        </div>
      </div>

      {/* Accordion course content */}
      <ChapterAccordion chapters={course.chapters} />
    </div>
  )
}