import { notFound } from "next/navigation";
import Link from "next/link";
import { BookOpen, ChevronLeft, Download, FileText } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Button,
} from "@/components/ui";
import { API_BASE_URL, getBook } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

function backendUrl(path?: string | null) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export default async function BookDetailPage({ params }: PageProps) {
  const { id } = await params;

  let data;
  try {
    data = await getBook(id);
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) {
      notFound();
    }
    throw err;
  }

  const { book } = data;
  const totalLessons = book.chapters.reduce(
    (sum, chapter) => sum + chapter.lessons.length,
    0
  );
  const pdfUrl = backendUrl(data.pdf_url);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          href="/course"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
          Quay lại danh sách
        </Link>
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              {book.title}
            </h1>
            {book.description && (
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {book.description}
              </p>
            )}
            <div className="mt-3 flex items-center gap-4 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <BookOpen className="h-4 w-4" />
                {book.chapters.length} chương
              </span>
              <span className="inline-flex items-center gap-1">
                <FileText className="h-4 w-4" />
                {totalLessons} bài học
              </span>
            </div>
          </div>
          {pdfUrl && (
            <a href={pdfUrl}>
              <Button>
                <Download className="mr-2 h-4 w-4" />
                Tải PDF
              </Button>
            </a>
          )}
        </div>
      </div>

      <Accordion type="single" collapsible className="w-full">
        {book.chapters.map((chapter, chapterIndex) => (
          <AccordionItem key={chapterIndex} value={`chapter-${chapterIndex}`}>
            <AccordionTrigger className="text-base font-medium">
              <span>{chapter.title}</span>
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                ({chapter.lessons.length} bài)
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-4">
                {chapter.description && (
                  <p className="text-sm leading-6 text-muted-foreground">
                    {chapter.description}
                  </p>
                )}
                <div className="space-y-3">
                  {chapter.lessons.map((lesson, lessonIndex) => (
                    <div key={lessonIndex} className="rounded-md border p-3">
                      <div className="font-medium">{lesson.title}</div>
                      {lesson.lecture && (
                        <p className="mt-2 text-sm leading-6 text-muted-foreground">
                          {lesson.lecture}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}
