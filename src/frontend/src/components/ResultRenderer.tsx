"use client";

import {
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FileVideo,
  Layers,
  ListChecks,
  Play,
  Presentation,
  Sparkles,
  Target,
} from "lucide-react";
import type { ReactNode } from "react";
import type { FeatureType } from "@/components/FeatureSelector";
import { API_BASE_URL, type GenerateResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

type PlainObject = Record<string, unknown>;

interface ResultRendererProps {
  feature: FeatureType;
  result: GenerateResponse;
}

const featureMeta: Record<
  FeatureType,
  { title: string; icon: ReactNode; tone: string }
> = {
  book: {
    title: "Book",
    icon: <BookOpen className="h-5 w-5" />,
    tone: "bg-blue-50 text-blue-700 ring-blue-200",
  },
  slide: {
    title: "Slide",
    icon: <Presentation className="h-5 w-5" />,
    tone: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  },
  quiz: {
    title: "Quiz",
    icon: <ClipboardCheck className="h-5 w-5" />,
    tone: "bg-rose-50 text-rose-700 ring-rose-200",
  },
  vid: {
    title: "Vid",
    icon: <FileVideo className="h-5 w-5" />,
    tone: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  },
};

function isObject(value: unknown): value is PlainObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown, fallback = "") {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stripInternalMarkers(value: string, compact = true) {
  const cleaned = value
    .replace(/===\s*BẮT ĐẦU.*?===/giu, " ")
    .replace(/===\s*KẾT THÚC.*?===/giu, " ")
    .replace(/\[MÃ ĐỊNH DANH TRANG:\s*\d+\]/giu, " ")
    .replace(/\bNỘI DUNG:\s*/giu, " ")
    .replace(/\bMã định danh trang\s+\d+\s+nội dung\b/giu, " ");

  if (compact) {
    return cleaned.replace(/\s+/g, " ").trim();
  }

  return cleaned.replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

function markdownLines(content: string) {
  return stripInternalMarkers(content, false).replace(/\r/g, "").split("\n");
}

function backendUrl(path?: string | null) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function MarkdownBlock({ content }: { content: string }) {
  const blocks: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="space-y-1 pl-5 text-sm leading-6">
          {listItems.map((item, index) => (
            <li key={`${item}-${index}`} className="list-disc">
              {item}
            </li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  markdownLines(content).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }

    const headingMatch = /^(#{1,3})\s+(.+)$/.exec(line);
    if (headingMatch) {
      flushList();
      blocks.push(
        <h4 key={`h-${blocks.length}`} className="text-base font-semibold leading-tight">
          {headingMatch[2].replace(/[*_`]/g, "")}
        </h4>
      );
      return;
    }

    const bulletMatch = /^[-*]\s+(.+)$/.exec(line);
    if (bulletMatch) {
      listItems.push(bulletMatch[1].replace(/[*_`]/g, ""));
      return;
    }

    flushList();
    blocks.push(
      <p key={`p-${blocks.length}`} className="text-sm leading-7 text-foreground/90">
        {line.replace(/[*_`]/g, "")}
      </p>
    );
  });

  flushList();
  return <div className="space-y-3">{blocks}</div>;
}

function textList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => stripInternalMarkers(asString(item))).filter(Boolean);
  }

  const text = stripInternalMarkers(asString(value), false);
  if (!text) return [];

  return text
    .split(/\n|;|•/)
    .map((item) => item.replace(/^[-*\d.)\s]+/, "").trim())
    .filter(Boolean);
}

function LessonList({
  title,
  icon,
  items,
}: {
  title: string;
  icon: ReactNode;
  items: string[];
}) {
  if (items.length === 0) return null;

  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </div>
      <ul className="space-y-1 pl-5 text-sm leading-6 text-muted-foreground">
        {items.map((item, index) => (
          <li key={`${item}-${index}`} className="list-disc">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function renderBook(result: GenerateResponse) {
  const book: PlainObject = isObject(result.book) ? result.book : {};
  const chapters = asArray(book.chapters);
  const lessonCount = chapters.reduce<number>((total, chapter) => {
    const item = isObject(chapter) ? chapter : {};
    return total + asArray(item.lessons).length;
  }, 0);
  const pdfUrl = backendUrl(result.pdf_url);

  return (
    <section className="space-y-6">
      <div className="rounded-lg border bg-card p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h3 className="text-2xl font-semibold">
              {asString(book.title, "Book từ tài liệu")}
            </h3>
            {Boolean(book.description) && (
              <p className="mt-2 max-w-3xl text-sm leading-7 text-muted-foreground">
                {asString(book.description)}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="rounded-md bg-muted px-3 py-2 text-center text-xs">
              <div className="font-semibold">{chapters.length}</div>
              <div className="text-muted-foreground">Chương</div>
            </div>
            <div className="rounded-md bg-muted px-3 py-2 text-center text-xs">
              <div className="font-semibold">{lessonCount}</div>
              <div className="text-muted-foreground">Bài</div>
            </div>
            {pdfUrl && (
              <a
                href={pdfUrl}
                className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Download className="h-4 w-4" />
                PDF
              </a>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {chapters.map((chapter, chapterIndex) => {
          const item = isObject(chapter) ? chapter : {};
          const lessons = asArray(item.lessons);

          return (
            <section key={chapterIndex} className="rounded-lg border bg-card">
              <div className="border-b p-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">
                    {chapterIndex + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="font-semibold leading-snug">
                      {asString(item.title, `Chương ${chapterIndex + 1}`)}
                    </h4>
                    {Boolean(item.description) && (
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        {asString(item.description)}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              <div className="divide-y">
                {lessons.map((lesson, lessonIndex) => {
                  const lessonObj = isObject(lesson) ? lesson : {};
                  const title = asString(
                    lessonObj.title ?? lesson,
                    `Bài ${chapterIndex + 1}.${lessonIndex + 1}`
                  );

                  return (
                    <details
                      key={lessonIndex}
                      className="group"
                      open={chapterIndex === 0 && lessonIndex === 0}
                    >
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4 hover:bg-muted/40">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold leading-snug">{title}</div>
                          {Boolean(lessonObj.duration) && (
                            <div className="mt-1 text-xs text-muted-foreground">
                              {asString(lessonObj.duration)}
                            </div>
                          )}
                        </div>
                        <span className="rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground group-open:hidden">
                          Mở
                        </span>
                        <span className="hidden rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground group-open:inline-flex">
                          Đóng
                        </span>
                      </summary>

                      <div className="space-y-5 px-4 pb-5">
                        <LessonList
                          title="Mục tiêu"
                          icon={<Target className="h-4 w-4" />}
                          items={textList(lessonObj.objectives)}
                        />
                        <div>
                          <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                            <BookOpen className="h-4 w-4" />
                            Nội dung bài giảng
                          </div>
                          <div className="rounded-lg bg-muted/40 p-4">
                            <MarkdownBlock
                              content={asString(
                                lessonObj.lecture,
                                "Chưa có nội dung bài giảng."
                              )}
                            />
                          </div>
                        </div>
                        <LessonList
                          title="Ý chính cần nhớ"
                          icon={<ListChecks className="h-4 w-4" />}
                          items={textList(lessonObj.key_points)}
                        />
                        {Boolean(lessonObj.activity) && (
                          <div>
                            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                              <Sparkles className="h-4 w-4" />
                              Hoạt động học tập
                            </div>
                            <p className="rounded-lg border bg-background p-3 text-sm leading-6 text-muted-foreground">
                              {stripInternalMarkers(asString(lessonObj.activity))}
                            </p>
                          </div>
                        )}
                        <LessonList
                          title="Kiểm tra nhanh"
                          icon={<ClipboardCheck className="h-4 w-4" />}
                          items={textList(lessonObj.assessment)}
                        />
                      </div>
                    </details>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}

function optionEntries(options: unknown) {
  return asArray(options).map((option, index) => ({
    key: String(index),
    label: String.fromCharCode(65 + index),
    value: asString(option),
  }));
}

function renderQuiz(result: GenerateResponse) {
  const questions = asArray(result.questions);

  return (
    <section className="grid gap-4">
      {questions.map((question, index) => {
        const item = isObject(question) ? question : {};
        const options = optionEntries(item.options);
        const correct = Number(item.correct ?? 0);

        return (
          <div key={index} className="rounded-lg border bg-card p-4">
            <div className="mb-3 flex items-start gap-3">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground">
                {index + 1}
              </div>
              <h4 className="font-semibold leading-snug">
                {asString(item.question, "Câu hỏi")}
              </h4>
            </div>

            <div className="grid gap-2 md:grid-cols-2">
              {options.map((option, optionIndex) => {
                const isCorrect = optionIndex === correct;
                return (
                  <div
                    key={option.key}
                    className={cn(
                      "flex items-start gap-2 rounded-md border p-3 text-sm",
                      isCorrect
                        ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                        : "bg-background"
                    )}
                  >
                    <span className="font-semibold">{option.label}.</span>
                    <span className="leading-5">{stripInternalMarkers(option.value)}</span>
                    {isCorrect && <CheckCircle2 className="ml-auto h-4 w-4 shrink-0" />}
                  </div>
                );
              })}
            </div>

            {Boolean(item.explanation) && (
              <p className="mt-3 rounded-md bg-muted/50 p-3 text-sm leading-6 text-muted-foreground">
                {stripInternalMarkers(asString(item.explanation))}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}

function renderSlide(result: GenerateResponse) {
  const slides = asArray(result.slides);

  return (
    <section className="grid gap-4 md:grid-cols-2">
      {slides.map((slide, index) => {
        const item = isObject(slide) ? slide : {};
        return (
          <div key={index} className="rounded-lg border bg-card p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-muted-foreground">
              <Layers className="h-4 w-4" />
              Slide {index + 1}
            </div>
            <h4 className="mb-3 text-lg font-semibold leading-tight">
              {asString(item.title, `Slide ${index + 1}`)}
            </h4>
            <MarkdownBlock content={asString(item.content, "")} />
            {Boolean(item.image_suggestion) && (
              <p className="mt-4 rounded-md bg-muted/50 p-3 text-xs leading-5 text-muted-foreground">
                {asString(item.image_suggestion)}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}

function renderVid(result: GenerateResponse) {
  const vid: PlainObject = isObject(result.vid) ? result.vid : {};
  const scenes = asArray(vid.scenes);
  const videoUrl = backendUrl(asString(vid.url));

  return (
    <section className="space-y-5">
      <div className="rounded-lg border bg-card p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-xl font-semibold">{asString(vid.filename, "vid.mp4")}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {asString(vid.duration_minutes, "3")} phút · {scenes.length} cảnh
            </p>
          </div>
          {videoUrl && (
            <a
              href={videoUrl}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Play className="h-4 w-4" />
              Mở video
            </a>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {scenes.map((scene, index) => {
          const item = isObject(scene) ? scene : {};
          return (
            <div key={index} className="rounded-lg border bg-card p-4">
              <div className="mb-3 text-xs font-semibold uppercase text-muted-foreground">
                Cảnh {index + 1}
              </div>
              <h4 className="mb-3 text-lg font-semibold">
                {asString(item.title, `Cảnh ${index + 1}`)}
              </h4>
              <MarkdownBlock content={asString(item.visual_text)} />
              {Boolean(item.voiceover) && (
                <p className="mt-4 rounded-md bg-muted/50 p-3 text-sm leading-6 text-muted-foreground">
                  {stripInternalMarkers(asString(item.voiceover))}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function renderFallback(result: GenerateResponse) {
  return (
    <pre className="max-h-[520px] overflow-auto rounded-lg bg-muted p-4 text-xs leading-relaxed">
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}

export default function ResultRenderer({ feature, result }: ResultRendererProps) {
  const meta = featureMeta[feature];

  const content = (() => {
    switch (feature) {
      case "book":
        return renderBook(result);
      case "slide":
        return renderSlide(result);
      case "quiz":
        return renderQuiz(result);
      case "vid":
        return renderVid(result);
      default:
        return renderFallback(result);
    }
  })();

  return (
    <div className="w-full max-w-5xl space-y-5">
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <span className={cn("rounded-md p-2 ring-1", meta.tone)}>{meta.icon}</span>
          <h2 className="text-xl font-semibold">{meta.title}</h2>
        </div>
        {content}
      </section>
    </div>
  );
}
