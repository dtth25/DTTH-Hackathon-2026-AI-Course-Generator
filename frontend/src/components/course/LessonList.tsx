"use client"

import { FileText } from "lucide-react"
import type { Lesson } from "@/types/course"
import { CitationBadge } from "./CitationBadge"

interface LessonListProps {
  lessons: Lesson[]
  chapterId: number
}

export function LessonList({ lessons, chapterId }: LessonListProps) {
  if (lessons.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic py-2">
        Chưa có bài học trong chương này
      </p>
    )
  }

  return (
    <div className="space-y-3">
      {lessons.map((lesson, index) => (
        <div
          key={lesson.id}
          className="ml-2 pl-4 border-l-2 border-blue-200 hover:border-blue-400 transition-colors"
        >
          <div className="flex items-start gap-2">
            <FileText className="h-4 w-4 mt-0.5 text-blue-500 shrink-0" />
            <div>
              <h4 className="text-sm font-semibold text-foreground">
                Bài {index + 1}: {lesson.title}
              </h4>
              {lesson.content && (
                <p className="text-sm text-muted-foreground mt-1 line-clamp-3">
                  {lesson.content}
                </p>
              )}
              {/* Citation-First: always display citations per lesson */}
              <CitationBadge citations={lesson.citations} />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}