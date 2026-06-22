"use client"

import {
  Accordion,
} from "@/components/ui/accordion"
import type { Chapter } from "@/types/course"
import { ChapterItem } from "./ChapterItem"

interface ChapterAccordionProps {
  chapters: Chapter[]
}

export function ChapterAccordion({ chapters }: ChapterAccordionProps) {
  if (chapters.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic text-center py-8">
        Khóa học chưa có chương nào
      </p>
    )
  }

  return (
    <Accordion type="single" collapsible className="w-full">
      {chapters.map((chapter, index) => (
        <ChapterItem
          key={chapter.id}
          chapter={chapter}
          index={index}
        />
      ))}
    </Accordion>
  )
}