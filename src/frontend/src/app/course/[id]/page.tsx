import { notFound } from "next/navigation";
import Link from "next/link";
import { BookOpen, FileText, ChevronLeft } from "lucide-react";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
  Button,
} from "@/components/ui";
import { getCourse } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function CourseDetailPage({ params }: PageProps) {
  const { id } = await params;

  let data;
  try {
    data = await getCourse(id);
  } catch (err) {
    if (err instanceof Error && err.message === "NOT_FOUND") {
      notFound();
    }
    // Lỗi khác (network, server) — throw để error boundary xử lý
    throw err;
  }

  const { course } = data;
  const totalLessons = course.chapters.reduce(
    (sum, ch) => sum + ch.lessons.length,
    0,
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <Link
          href="/course"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Quay lại danh sách
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {course.title}
        </h1>
        {course.description && (
          <p className="text-sm text-muted-foreground">{course.description}</p>
        )}
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <BookOpen className="h-4 w-4" />
            {course.chapters.length} chương
          </span>
          <span className="inline-flex items-center gap-1">
            <FileText className="h-4 w-4" />
            {totalLessons} bài học
          </span>
        </div>
      </div>

      {/* Accordion */}
      <Accordion type="single" collapsible className="w-full">
        {course.chapters.map((chapter, idx) => (
          <AccordionItem key={idx} value={`chapter-${idx}`}>
            <AccordionTrigger className="text-base font-medium">
              <span>{chapter.title}</span>
              <span className="ml-2 text-xs text-muted-foreground font-normal">
                ({chapter.lessons.length} bài)
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <ul className="space-y-1">
                {chapter.lessons.map((lesson, lessonIdx) => (
                  <li
                    key={lessonIdx}
                    className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
                  >
                    <FileText className="h-4 w-4 shrink-0" />
                    <span>{lesson.title}</span>
                  </li>
                ))}
              </ul>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>

      {/* Bottom action */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Link href={`/quiz/${id}`}>
            <Button variant="default">📋 Làm quiz</Button>
          </Link>
          <Link href={`/flashcards/${id}`}>
            <Button variant="outline">🎴 Flashcards</Button>
          </Link>
          <Link href={`/slides/${id}`}>
            <Button variant="outline">📊 Slides</Button>
          </Link>
          <Link href={`/mindmap/${id}`}>
            <Button variant="outline">🧠 Mind Map</Button>
          </Link>
        </div>
        <Link href="/course">
          <Button variant="ghost">Quay lại danh sách</Button>
        </Link>
      </div>
    </div>
  );
}