"use client"

import { BookOpen } from "lucide-react"
import {
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import type { Chapter } from "@/types/course"
import { LessonList } from "./LessonList"

interface ChapterItemProps {
  chapter: Chapter
  index: number
}

export function ChapterItem({ chapter, index }: ChapterItemProps) {
  const lessonCount = chapter.lessons.length

  return (
    <AccordionItem value={`chapter-${chapter.id}`}>
      <AccordionTrigger className="hover:no-underline">
        <div className="flex items-center gap-3 text-left">
          <BookOpen className="h-5 w-5 text-blue-500 shrink-0" />
          <span className="font-semibold text-base">
            Chương {index + 1}: {chapter.title}
          </span>
          <Badge variant="secondary" className="ml-2 text-xs">
            {lessonCount} bài
          </Badge>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <LessonList lessons={chapter.lessons} chapterId={chapter.id} />
      </AccordionContent>
    </AccordionItem>
  )
}