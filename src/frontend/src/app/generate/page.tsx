"use client";

import { useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  CircleAlert,
  FileText,
  Loader2,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import FeatureSelector, { type FeatureType } from "@/components/FeatureSelector";
import PromptInput from "@/components/PromptInput";
import ResultRenderer from "@/components/ResultRenderer";
import UploadBox from "@/components/UploadBox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type CourseStatusResponse,
  type GenerateResponse,
  type UploadResponse,
  generateContent,
  getCourseStatus,
} from "@/lib/api";

type CourseStatus = CourseStatusResponse["status"] | "idle";
type OutputMap = Partial<Record<FeatureType, GenerateResponse>>;

const OUTPUT_ORDER: FeatureType[] = ["book", "slide", "quiz", "vid"];
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function statusCopy(status: CourseStatus) {
  switch (status) {
    case "ready":
      return "Tài liệu đã sẵn sàng";
    case "failed":
      return "Phân tích tài liệu thất bại";
    case "processing":
    case "pending":
      return "Đang phân tích tài liệu";
    case "unknown":
      return "Chưa tìm thấy tài liệu";
    default:
      return "Chưa có tài liệu";
  }
}

export default function GeneratePage() {
  const [selectedFeature, setSelectedFeature] = useState<FeatureType>("book");
  const [generatingFeature, setGeneratingFeature] = useState<FeatureType | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [courseId, setCourseId] = useState("");
  const [filenames, setFilenames] = useState<string[]>([]);
  const [courseStatus, setCourseStatus] = useState<CourseStatus>("idle");
  const [outputs, setOutputs] = useState<OutputMap>({});

  const pollCourseStatus = async (id: string) => {
    setIsPolling(true);
    setCourseStatus("processing");

    try {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const status = await getCourseStatus(id);
        setCourseStatus(status.status);
        if (status.filenames?.length) setFilenames(status.filenames);

        if (status.status === "ready") {
          toast.success("Tài liệu đã sẵn sàng để tạo nội dung.");
          return;
        }

        if (status.status === "failed") {
          throw new Error(status.error || "Không phân tích được tài liệu.");
        }

        await wait(2000);
      }

      throw new Error("Tài liệu xử lý quá lâu. Vui lòng thử lại sau.");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Không kiểm tra được trạng thái tài liệu.";
      setCourseStatus("failed");
      toast.error(message);
    } finally {
      setIsPolling(false);
    }
  };

  const handleUploaded = (upload: UploadResponse) => {
    setCourseId(upload.course_id);
    setFilenames(upload.filenames?.length ? upload.filenames : [upload.filename]);
    setOutputs({});
    void pollCourseStatus(upload.course_id);
  };

  const handlePromptSubmit = async (prompt: string) => {
    if (!courseId) {
      toast.error("Vui lòng tải tài liệu lên trước.");
      return;
    }

    if (courseStatus !== "ready") {
      toast.error("Tài liệu chưa sẵn sàng để tạo nội dung.");
      return;
    }

    setGeneratingFeature(selectedFeature);

    try {
      const response = await generateContent(selectedFeature, courseId, prompt);
      setOutputs((prev) => ({ ...prev, [selectedFeature]: response }));
      toast.success(`Đã tạo ${selectedFeature.toUpperCase()}.`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Có lỗi xảy ra khi tạo nội dung.";
      toast.error(message);
    } finally {
      setGeneratingFeature(null);
    }
  };

  const status = statusCopy(courseStatus);
  const hasOutputs = OUTPUT_ORDER.some((feature) => outputs[feature]);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-8">
      <section className="mb-8 grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
        <div className="space-y-4">
          <div className="inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm text-muted-foreground">
            <Sparkles className="h-4 w-4 text-amber-600" />
            Book, Slide, Quiz và Vid từ tài liệu của bạn
          </div>
          <div className="space-y-3">
            <h1 className="max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
              Tạo bộ học liệu từ một hoặc nhiều tài liệu
            </h1>
            <p className="max-w-2xl text-base leading-7 text-muted-foreground">
              Tải lên PDF, DOCX hoặc TXT, chọn output cần tạo và giữ tất cả kết quả
              trong cùng một workspace.
            </p>
          </div>
        </div>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              {courseStatus === "ready" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              ) : courseStatus === "failed" ? (
                <CircleAlert className="h-4 w-4 text-destructive" />
              ) : courseStatus === "idle" ? (
                <FileText className="h-4 w-4 text-muted-foreground" />
              ) : (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              )}
              {status}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            {courseId ? (
              <>
                <p>Mã tài liệu: {courseId}</p>
                <p>{filenames.length} file trong bộ tài liệu</p>
                {filenames.length > 0 && (
                  <div className="max-h-24 space-y-1 overflow-auto rounded-md bg-muted/50 p-2">
                    {filenames.map((name) => (
                      <div key={name} className="truncate">
                        {name}
                      </div>
                    ))}
                  </div>
                )}
                {isPolling && <p>Vui lòng chờ trong khi hệ thống đọc tài liệu.</p>}
              </>
            ) : (
              <p>Tải tài liệu lên để bắt đầu tạo học liệu.</p>
            )}
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <aside className="space-y-6">
          <UploadBox onUploaded={handleUploaded} />
          <Card>
            <CardContent className="space-y-6 p-5">
              <FeatureSelector selected={selectedFeature} onSelect={setSelectedFeature} />
              <PromptInput
                onSubmit={handlePromptSubmit}
                isLoading={generatingFeature === selectedFeature}
                disabled={!courseId || courseStatus !== "ready" || Boolean(generatingFeature)}
              />
            </CardContent>
          </Card>
        </aside>

        <section className="min-w-0 space-y-6">
          {!hasOutputs && (
            <div className="flex min-h-[420px] flex-col items-center justify-center rounded-lg border bg-card p-8 text-center">
              <BookOpen className="mb-4 h-10 w-10 text-muted-foreground" />
              <h2 className="text-xl font-semibold">Chưa có output nào</h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                Sau khi tài liệu sẵn sàng, chọn Book, Slide, Quiz hoặc Vid rồi nhấn Tạo.
              </p>
            </div>
          )}

          {OUTPUT_ORDER.map((feature) => {
            const result = outputs[feature];
            if (!result) return null;
            return <ResultRenderer key={feature} feature={feature} result={result} />;
          })}
        </section>
      </div>
    </div>
  );
}
