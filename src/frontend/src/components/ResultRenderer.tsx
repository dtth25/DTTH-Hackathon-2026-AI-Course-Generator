"use client";

import { useState, type ReactNode } from "react";
import {
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Download,
  FileVideo,
  Layers,
  ListChecks,
  Presentation,
  RotateCcw,
  Sparkles,
  Target,
  XCircle,
} from "lucide-react";
import type { FeatureType } from "@/components/FeatureSelector";
import { buttonVariants } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
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
    tone: "bg-sky-50 text-sky-700 ring-sky-200",
  },
  slide: {
    title: "Slide",
    icon: <Presentation className="h-5 w-5" />,
    tone: "bg-violet-50 text-violet-700 ring-violet-200",
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
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function backendUrl(path?: string | null) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function stripInternalMarkers(value: string, compact = true) {
  const cleaned = value
    .replace(/===\s*BẮT ĐẦU.*?===/giu, " ")
    .replace(/===\s*KẾT THÚC.*?===/giu, " ")
    .replace(/\[MÃ ĐỊNH DANH TRANG:\s*\d+\]/giu, " ")
    .replace(/\bNỘI DUNG:\s*/giu, " ")
    .replace(/\b(page|source|chunk_id)\s*:\s*[^,\n]+/giu, " ");

  if (compact) return cleaned.replace(/\s+/g, " ").trim();
  return cleaned.replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

function markdownLines(content: string) {
  return stripInternalMarkers(content, false).replace(/\r/g, "").split("\n");
}

function MarkdownBlock({ content }: { content: string }) {
  const blocks: ReactNode[] = [];
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

function DownloadLink({
  href,
  label,
  icon,
  variant = "outline",
}: {
  href?: string | null;
  label: string;
  icon: ReactNode;
  variant?: "default" | "outline" | "secondary" | "ghost";
}) {
  const resolved = backendUrl(href);
  if (!resolved) return null;

  return (
    <a
      href={resolved}
      className={buttonVariants({ variant, size: "lg" })}
      target="_blank"
      rel="noreferrer"
    >
      {icon}
      {label}
    </a>
  );
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

function BookResult({ result }: { result: GenerateResponse }) {
  const book: PlainObject = isObject(result.book) ? result.book : {};
  const chapters = asArray(book.chapters);
  const lessonCount = chapters.reduce<number>((total, chapter) => {
    const item = isObject(chapter) ? chapter : {};
    return total + asArray(item.lessons).length;
  }, 0);

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
            <DownloadLink
              href={result.pdf_url}
              label="Tải PDF"
              icon={<Download className="h-4 w-4" />}
              variant="default"
            />
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
                            Nội dung bài học
                          </div>
                          <div className="rounded-lg bg-muted/40 p-4">
                            <MarkdownBlock
                              content={asString(
                                lessonObj.lecture,
                                "Chưa có nội dung bài học."
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

function SlideResult({ result }: { result: GenerateResponse }) {
  const slides = asArray(result.slides);
  const [currentIndex, setCurrentIndex] = useState(0);
  const current = isObject(slides[currentIndex]) ? slides[currentIndex] : {};
  const progress = slides.length ? ((currentIndex + 1) / slides.length) * 100 : 0;

  if (slides.length === 0) {
    return <EmptyResult message="Chưa có slide để hiển thị." />;
  }

  return (
    <section className="space-y-4">
      <div className="rounded-lg border bg-card p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
              <Layers className="h-4 w-4" />
              Slide {currentIndex + 1} / {slides.length}
            </div>
            <h3 className="text-2xl font-semibold leading-tight">
              {asString(current.title, `Slide ${currentIndex + 1}`)}
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <DownloadLink
              href={result.pdf_url}
              label="PDF"
              icon={<Download className="h-4 w-4" />}
              variant="default"
            />
          </div>
        </div>

        <Progress value={progress} className="mb-5 h-2" />
        <div className="min-h-[320px] rounded-lg border bg-background p-6">
          <MarkdownBlock content={asString(current.content, "")} />
          {Boolean(current.image_suggestion) && (
            <p className="mt-6 rounded-md bg-muted/50 p-3 text-sm leading-6 text-muted-foreground">
              Gợi ý hình ảnh: {asString(current.image_suggestion)}
            </p>
          )}
        </div>

        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            type="button"
            className={buttonVariants({ variant: "outline", size: "lg" })}
            onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
            disabled={currentIndex === 0}
          >
            <ChevronLeft className="h-4 w-4" />
            Trước
          </button>
          <button
            type="button"
            className={buttonVariants({ variant: "outline", size: "lg" })}
            onClick={() =>
              setCurrentIndex((prev) => Math.min(slides.length - 1, prev + 1))
            }
            disabled={currentIndex === slides.length - 1}
          >
            Tiếp
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {slides.map((slide, index) => {
          const item = isObject(slide) ? slide : {};
          return (
            <button
              key={index}
              type="button"
              onClick={() => setCurrentIndex(index)}
              className={cn(
                "min-w-40 rounded-md border p-3 text-left text-xs transition-colors",
                currentIndex === index
                  ? "border-primary bg-primary/10"
                  : "bg-card hover:bg-muted/60"
              )}
            >
              <div className="mb-1 font-semibold">Slide {index + 1}</div>
              <div className="line-clamp-2 text-muted-foreground">
                {asString(item.title, "Nội dung")}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function QuizResult({ result }: { result: GenerateResponse }) {
  const questions = asArray(result.questions);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [submitted, setSubmitted] = useState(false);
  const current = isObject(questions[currentIndex]) ? questions[currentIndex] : {};
  const options = optionEntries(current.options);
  const correct = Number(current.correct ?? 0);
  const selected = answers[currentIndex];
  const answeredCount = Object.keys(answers).length;
  const progress = questions.length ? ((currentIndex + 1) / questions.length) * 100 : 0;

  const score = submitted
    ? questions.reduce<number>((total, question, index) => {
        const item = isObject(question) ? question : {};
        return total + (answers[index] === Number(item.correct ?? 0) ? 1 : 0);
      }, 0)
    : 0;

  if (questions.length === 0) {
    return <EmptyResult message="Chưa có câu hỏi để hiển thị." />;
  }

  const resetQuiz = () => {
    setAnswers({});
    setSubmitted(false);
    setCurrentIndex(0);
  };

  return (
    <section className="space-y-4">
      <div className="rounded-lg border bg-card p-5">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
              <ClipboardCheck className="h-4 w-4" />
              Câu {currentIndex + 1} / {questions.length}
            </div>
            <h3 className="text-xl font-semibold leading-snug">
              {asString(current.question, "Câu hỏi")}
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <DownloadLink
              href={result.pdf_url}
              label="PDF"
              icon={<Download className="h-4 w-4" />}
              variant="default"
            />
          </div>
        </div>

        <Progress value={progress} className="mb-5 h-2" />

        {submitted && (
          <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
            Kết quả: {score}/{questions.length} câu đúng
          </div>
        )}

        <div className="grid gap-3">
          {options.map((option, optionIndex) => {
            const isSelected = selected === optionIndex;
            const isCorrect = optionIndex === correct;
            const isWrongSelection = submitted && isSelected && !isCorrect;

            return (
              <button
                key={option.key}
                type="button"
                disabled={submitted}
                onClick={() =>
                  setAnswers((prev) => ({ ...prev, [currentIndex]: optionIndex }))
                }
                className={cn(
                  "flex items-start gap-3 rounded-md border p-4 text-left text-sm transition-colors",
                  !submitted && isSelected && "border-primary bg-primary/10",
                  !submitted && !isSelected && "bg-background hover:bg-muted/50",
                  submitted && isCorrect && "border-emerald-300 bg-emerald-50 text-emerald-950",
                  isWrongSelection && "border-rose-300 bg-rose-50 text-rose-950"
                )}
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold">
                  {option.label}
                </span>
                <span className="leading-6">{stripInternalMarkers(option.value)}</span>
                {submitted && isCorrect && (
                  <CheckCircle2 className="ml-auto h-4 w-4 shrink-0" />
                )}
                {isWrongSelection && <XCircle className="ml-auto h-4 w-4 shrink-0" />}
              </button>
            );
          })}
        </div>

        {submitted && Boolean(current.explanation) && (
          <p className="mt-4 rounded-md bg-muted/50 p-3 text-sm leading-6 text-muted-foreground">
            {stripInternalMarkers(asString(current.explanation))}
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            className={buttonVariants({ variant: "outline", size: "lg" })}
            onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
            disabled={currentIndex === 0}
          >
            <ChevronLeft className="h-4 w-4" />
            Trước
          </button>

          <div className="flex flex-wrap gap-2">
            {!submitted ? (
              <button
                type="button"
                className={buttonVariants({ variant: "default", size: "lg" })}
                onClick={() => setSubmitted(true)}
              >
                Nộp bài ({answeredCount}/{questions.length})
              </button>
            ) : (
              <button
                type="button"
                className={buttonVariants({ variant: "secondary", size: "lg" })}
                onClick={resetQuiz}
              >
                <RotateCcw className="h-4 w-4" />
                Làm lại
              </button>
            )}
          </div>

          <button
            type="button"
            className={buttonVariants({ variant: "outline", size: "lg" })}
            onClick={() =>
              setCurrentIndex((prev) => Math.min(questions.length - 1, prev + 1))
            }
            disabled={currentIndex === questions.length - 1}
          >
            Tiếp
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  );
}

function VidResult({ result }: { result: GenerateResponse }) {
  const vid: PlainObject = isObject(result.vid) ? result.vid : {};
  const scenes = asArray(vid.scenes);
  const videoUrl = backendUrl(asString(vid.url));
  const failed = vid.status === "failed";

  return (
    <section className="space-y-5">
      <div className="rounded-lg border bg-card p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-xl font-semibold">
              {failed ? "Chưa tạo được video" : asString(vid.filename, "vid.mp4")}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {asString(vid.duration_minutes, "3")} phút · {scenes.length} cảnh
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <DownloadLink
              href={asString(vid.url)}
              label="Tải MP4"
              icon={<Download className="h-4 w-4" />}
              variant="default"
            />
          </div>
        </div>

        {failed && (
          <p className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            {asString(vid.error, "Video chưa được tạo. Vui lòng thử lại sau.")}
          </p>
        )}

        {videoUrl && !failed && (
          <video
            className="mt-5 aspect-video w-full rounded-lg border bg-black"
            src={videoUrl}
            controls
          />
        )}
      </div>

      {scenes.length > 0 && (
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
      )}
    </section>
  );
}

function EmptyResult({ message }: { message: string }) {
  return (
    <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
      {message}
    </div>
  );
}

function JsonFallback({ result }: { result: GenerateResponse }) {
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
        return <BookResult result={result} />;
      case "slide":
        return <SlideResult result={result} />;
      case "quiz":
        return <QuizResult result={result} />;
      case "vid":
        return <VidResult result={result} />;
      default:
        return <JsonFallback result={result} />;
    }
  })();

  return (
    <div className="w-full space-y-5">
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
