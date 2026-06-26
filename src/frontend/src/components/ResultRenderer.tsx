"use client";

import { useState, type ReactNode } from "react";
import {
  BookOpen,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Copy,
  Download,
  FileJson,
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
import { KaTeXText } from "@/components/KaTeXRenderer";

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
  return cleaned.replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n");
}

function cleanContentMarkdown(content: string): string {
  const parts = content.split(/(\$\$[\s\S]*?\$\$|\$[\s\S]*?\$)/g);
  return parts
    .map((part) => {
      if (part && part.startsWith("$")) {
        return part;
      }
      // Keep backticks (`) to preserve code blocks styling
      return part ? part.replace(/[*_]/g, "") : part;
    })
    .join("");
}

export function replaceNewlinesOutsideMath(content: string): string {
  const parts = content.split(/(\$\$[\s\S]*?\$\$|\$[\s\S]*?\$)/g);
  return parts
    .map((part) => {
      if (part && part.startsWith("$")) {
        // Inside math blocks, replace literal \n unless followed by a valid LaTeX command starting with n
        return part.replace(/\\n(?![eui](?![a-zA-Z])|[a-zA-Z]{2,})/g, "\n");
      }
      return part ? part.replace(/\\n/g, "\n") : part;
    })
    .join("");
}

function highlightCode(code: string, language = ""): string {
  const isPython = ["python", "py"].includes(language.toLowerCase());

  const tokenRegex = isPython
    ? /((?:#.*))|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^\'\\])*')|(\b\d+(?:\.\d+)?\b)|(@[a-zA-Z_][a-zA-Z0-9_]*)|(\b(?:def|class|import|from|as|return|if|else|elif|while|for|in|and|or|not|with|try|except|pass|assert|break|continue|yield|lambda|global|nonlocal|del)\b)|(\b[a-zA-Z_][a-zA-Z0-9_]*)(?=\s*\()|([a-zA-Z_][a-zA-Z0-9_]*)/g
    : /((?:\/\/.*|\/\*[\s\S]*?\*\/))|("(?:\\.|[^"\\])*"|'(?:\\.|[^\'\\])*'|`(?:\\.|[^\`\\])*`)|(\b\d+(?:\.\d+)?\b)|(\b(?:function|class|const|let|var|return|if|else|switch|case|default|while|for|in|of|break|continue|import|from|export|default|try|catch|finally|throw|new|this|async|await|yield|true|false|null|undefined|NaN)\b)|(\b[a-zA-Z_][a-zA-Z0-9_]*)(?=\s*\()|([a-zA-Z_][a-zA-Z0-9_]*)/g;

  let lastIndex = 0;
  let html = "";
  let match;

  const escapeHtml = (text: string) => {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  };

  while ((match = tokenRegex.exec(code)) !== null) {
    if (match.index > lastIndex) {
      html += escapeHtml(code.slice(lastIndex, match.index));
    }

    const [
      full,
      comment,
      str,
      num,
      decoratorOrKeyword,
      keywordOrFunc,
      funcOrWord,
      otherWord
    ] = match;

    if (comment !== undefined) {
      html += `<span class="text-zinc-500 italic">${escapeHtml(comment)}</span>`;
    } else if (str !== undefined) {
      html += `<span class="text-emerald-400">${escapeHtml(str)}</span>`;
    } else if (num !== undefined) {
      html += `<span class="text-amber-400">${escapeHtml(num)}</span>`;
    } else if (isPython) {
      const decorator = decoratorOrKeyword;
      const keyword = keywordOrFunc;
      const func = funcOrWord;
      const word = otherWord;

      if (decorator !== undefined) {
        html += `<span class="text-yellow-400 font-mono">${escapeHtml(decorator)}</span>`;
      } else if (keyword !== undefined) {
        if (["True", "False", "None", "self"].includes(keyword)) {
          html += `<span class="text-violet-400 font-semibold">${escapeHtml(keyword)}</span>`;
        } else {
          html += `<span class="text-pink-400 font-semibold">${escapeHtml(keyword)}</span>`;
        }
      } else if (func !== undefined) {
        html += `<span class="text-sky-400">${escapeHtml(func)}</span>`;
      } else if (word !== undefined) {
        html += escapeHtml(word);
      }
    } else {
      const keyword = decoratorOrKeyword;
      const func = keywordOrFunc;
      const word = funcOrWord;

      if (keyword !== undefined) {
        if (["true", "false", "null", "undefined", "NaN"].includes(keyword)) {
          html += `<span class="text-violet-400 font-semibold">${escapeHtml(keyword)}</span>`;
        } else {
          html += `<span class="text-pink-400 font-semibold">${escapeHtml(keyword)}</span>`;
        }
      } else if (func !== undefined) {
        html += `<span class="text-sky-400">${escapeHtml(func)}</span>`;
      } else if (word !== undefined) {
        html += escapeHtml(word);
      }
    }

    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < code.length) {
    html += escapeHtml(code.slice(lastIndex));
  }

  return html;
}

function PrettyCodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy code: ", err);
    }
  };

  return (
    <div className="my-5 overflow-hidden rounded-xl border border-zinc-200 shadow-sm dark:border-zinc-800">
      {/* Code Box Header */}
      <div className="flex items-center justify-between bg-zinc-50 px-4 py-2 dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-red-400/80" />
          <span className="h-3 w-3 rounded-full bg-yellow-400/80" />
          <span className="h-3 w-3 rounded-full bg-green-400/80" />
        </div>
        <div className="flex items-center gap-3">
          {language && (
            <span className="text-[11px] font-semibold tracking-wider text-zinc-500 uppercase select-none dark:text-zinc-400 font-mono">
              {language}
            </span>
          )}
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 rounded bg-zinc-200/50 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 p-1 px-2 text-xs font-medium text-zinc-600 transition-colors dark:text-zinc-300 cursor-pointer"
            title="Sao chép mã"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                <span className="text-[10px] text-green-600 dark:text-green-400 font-semibold">Đã chép</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span className="text-[10px]">Sao chép</span>
              </>
            )}
          </button>
        </div>
      </div>
      {/* Code Box Body */}
      <div className="relative bg-zinc-950 p-4 font-mono text-xs text-zinc-100 overflow-x-auto max-w-full leading-relaxed">
        <pre className="whitespace-pre">
          <code dangerouslySetInnerHTML={{ __html: highlightCode(code, language) }} />
        </pre>
      </div>
    </div>
  );
}

export function MarkdownBlock({ content }: { content: string }) {
  const processed = replaceNewlinesOutsideMath(content);
  const cleaned = stripInternalMarkers(processed, false).replace(/\r/g, "");

  const lines = cleaned.split("\n");
  const blocks: ReactNode[] = [];
  
  let currentListItems: string[] = [];
  let currentParagraphLines: string[] = [];
  let inCodeBlock = false;
  let codeBlockLanguage = "";
  let codeBlockLines: string[] = [];
  let keyCounter = 0;

  const flushParagraph = () => {
    if (currentParagraphLines.length > 0) {
      const text = cleanContentMarkdown(currentParagraphLines.join(" "));
      blocks.push(
        <p key={`p-${keyCounter++}`} className="text-sm leading-7 text-foreground/90">
          <KaTeXText>{text}</KaTeXText>
        </p>
      );
      currentParagraphLines = [];
    }
  };

  const flushList = () => {
    if (currentListItems.length > 0) {
      blocks.push(
        <ul key={`ul-${keyCounter++}`} className="space-y-1 pl-5 text-sm leading-6">
          {currentListItems.map((item, index) => (
            <li key={`li-${index}`} className="list-disc text-foreground/90">
              <KaTeXText>{cleanContentMarkdown(item)}</KaTeXText>
            </li>
          ))}
        </ul>
      );
      currentListItems = [];
    }
  };

  const flushCodeBlock = () => {
    if (codeBlockLines.length > 0) {
      blocks.push(
        <PrettyCodeBlock
          key={`code-${keyCounter++}`}
          language={codeBlockLanguage}
          code={codeBlockLines.join("\n")}
        />
      );
      codeBlockLines = [];
      inCodeBlock = false;
      codeBlockLanguage = "";
    }
  };

  const flushAll = () => {
    flushParagraph();
    flushList();
    flushCodeBlock();
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Handle Code Block
    if (trimmed.startsWith("```") || (inCodeBlock && trimmed.startsWith("``"))) {
      if (inCodeBlock) {
        flushCodeBlock();
      } else {
        flushAll();
        inCodeBlock = true;
        codeBlockLanguage = trimmed.slice(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      continue;
    }

    // Handle Headers
    const headingMatch = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (headingMatch) {
      flushAll();
      blocks.push(
        <h4 key={`h-${keyCounter++}`} className="text-base font-semibold leading-tight mt-4 text-foreground">
          <KaTeXText>{cleanContentMarkdown(headingMatch[2])}</KaTeXText>
        </h4>
      );
      continue;
    }

    // Handle Lists
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      flushParagraph();
      const cleanLine = trimmed.replace(/^[-*]\s+/, "");
      currentListItems.push(cleanLine);
      continue;
    }

    // Handle Empty Line
    if (trimmed === "") {
      flushAll();
      continue;
    }

    // Regular line (append to paragraph or list item)
    if (currentListItems.length > 0) {
      currentListItems[currentListItems.length - 1] += " " + trimmed;
    } else {
      currentParagraphLines.push(trimmed);
    }
  }

  flushAll();

  return <div className="space-y-3 break-words max-w-full overflow-x-auto">{blocks}</div>;
}

function textList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => replaceNewlinesOutsideMath(stripInternalMarkers(asString(item))))
      .filter(Boolean);
  }

  const text = replaceNewlinesOutsideMath(stripInternalMarkers(asString(value), false));
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

function LessonMarkdownSection({
  title,
  icon,
  content,
}: {
  title: string;
  icon: ReactNode;
  content: unknown;
}) {
  if (!content) return null;

  const markdownContent = (() => {
    if (Array.isArray(content)) {
      const items = content
        .map((item) => {
          const str = asString(item).trim();
          if (!str) return "";
          if (str.startsWith("- ") || str.startsWith("* ")) return str;
          return `- ${str}`;
        })
        .filter(Boolean);
      return items.length > 0 ? items.join("\n") : "";
    }
    return asString(content).trim();
  })();

  if (!markdownContent) return null;

  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </div>
      <div className="rounded-lg border bg-background p-3 text-sm leading-6 text-muted-foreground">
        <MarkdownBlock content={markdownContent} />
      </div>
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
                        <LessonMarkdownSection
                          title="Mục tiêu"
                          icon={<Target className="h-4 w-4" />}
                          content={lessonObj.objectives}
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
                        <LessonMarkdownSection
                          title="Ý chính cần nhớ"
                          icon={<ListChecks className="h-4 w-4" />}
                          content={lessonObj.key_points}
                        />
                        {Boolean(lessonObj.activity) && (
                          <div>
                            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                              <Sparkles className="h-4 w-4" />
                              Hoạt động học tập
                            </div>
                            <div className="rounded-lg border bg-background p-3 text-sm leading-6 text-muted-foreground">
                              <MarkdownBlock content={asString(lessonObj.activity)} />
                            </div>
                          </div>
                        )}
                        <LessonMarkdownSection
                          title="Kiểm tra nhanh"
                          icon={<ClipboardCheck className="h-4 w-4" />}
                          content={lessonObj.assessment}
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
            <DownloadLink
              href={result.json_url}
              label="JSON"
              icon={<FileJson className="h-4 w-4" />}
              variant="outline"
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
              <KaTeXText>{asString(current.question, "Câu hỏi")}</KaTeXText>
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <DownloadLink
              href={result.pdf_url}
              label="PDF"
              icon={<Download className="h-4 w-4" />}
              variant="default"
            />
            <DownloadLink
              href={result.json_url}
              label="JSON"
              icon={<FileJson className="h-4 w-4" />}
              variant="outline"
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
                <span className="leading-6"><KaTeXText>{stripInternalMarkers(option.value)}</KaTeXText></span>
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
            <KaTeXText>{stripInternalMarkers(asString(current.explanation))}</KaTeXText>
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
