"use client";

import { useState } from "react";
import { toast } from "sonner";
import UploadBox from "@/components/UploadBox";
import FeatureSelector, { type FeatureType } from "@/components/FeatureSelector";
import PromptInput from "@/components/PromptInput";
import ResultRenderer from "@/components/ResultRenderer";
import {
  type CourseStatusResponse,
  type GenerateResponse,
  type UploadResponse,
  generateContent,
  getCourseStatus,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FileText,
  BookOpen,
  Sparkles,
  CheckCircle2,
  CircleAlert,
  Loader2,
} from "lucide-react";

type CourseStatus = CourseStatusResponse["status"] | "idle";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default function GeneratePage() {
  const [selectedFeature, setSelectedFeature] = useState<FeatureType | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [courseId, setCourseId] = useState("");
  const [filename, setFilename] = useState("");
  const [courseStatus, setCourseStatus] = useState<CourseStatus>("idle");
  const [result, setResult] = useState<GenerateResponse | null>(null);

  const pollCourseStatus = async (id: string) => {
    setIsPolling(true);
    setCourseStatus("processing");

    try {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const status = await getCourseStatus(id);
        setCourseStatus(status.status);

        if (status.status === "ready") {
          toast.success("Tài liệu đã sẵn sàng.");
          return;
        }

        if (status.status === "failed") {
          throw new Error(status.error || "Xử lý tài liệu thất bại.");
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
    setFilename(upload.filename);
    setResult(null);
    void pollCourseStatus(upload.course_id);
  };

  const handlePromptSubmit = async (prompt: string) => {
    if (!courseId) {
      toast.error("Vui lòng upload tài liệu trước.");
      return;
    }

    if (courseStatus !== "ready") {
      toast.error("Tài liệu chưa xử lý xong.");
      return;
    }

    if (!selectedFeature) {
      toast.error("Vui lòng chọn một tính năng trước khi gửi yêu cầu.");
      return;
    }

    setIsProcessing(true);
    setResult(null);

    try {
      const response = await generateContent(selectedFeature, courseId, prompt);
      setResult(response);
      toast.success("Đã tạo nội dung.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Có lỗi xảy ra khi tạo nội dung.";
      toast.error(message);
    } finally {
      setIsProcessing(false);
    }
  };

  const statusLabel =
    courseStatus === "ready"
      ? "Ready"
      : courseStatus === "failed"
        ? "Failed"
        : courseStatus === "idle"
          ? "No file"
          : "Processing";

  return (
    <div className="flex min-h-screen flex-col items-center px-4 py-8">
      <div className="mb-8 max-w-2xl text-center">
        <div className="mb-4 inline-flex items-center justify-center rounded-full bg-primary/10 p-2">
          <Sparkles className="h-6 w-6 text-primary" />
        </div>
        <h1 className="mb-4 text-3xl font-bold tracking-tight sm:text-4xl">
          Tạo Nội Dung Từ Tài Liệu Của Bạn
        </h1>
        <p className="text-lg text-muted-foreground">
          Tải lên PDF, DOCX hoặc TXT, chọn tính năng và để AI tự động tạo nội dung
          học tập cho bạn.
        </p>
      </div>

      <div className="mb-8 grid w-full max-w-2xl grid-cols-1 gap-6 md:grid-cols-3">
        <div className="flex flex-col items-center rounded-lg border bg-card p-4 text-center">
          <div className="mb-3 rounded-full bg-primary/10 p-2">
            <FileText className="h-5 w-5 text-primary" />
          </div>
          <h3 className="mb-1 text-sm font-semibold">1. Tải lên tài liệu</h3>
          <p className="text-xs text-muted-foreground">PDF, DOCX hoặc TXT</p>
        </div>
        <div className="flex flex-col items-center rounded-lg border bg-card p-4 text-center">
          <div className="mb-3 rounded-full bg-primary/10 p-2">
            <Sparkles className="h-5 w-5 text-primary" />
          </div>
          <h3 className="mb-1 text-sm font-semibold">2. Chọn output</h3>
          <p className="text-xs text-muted-foreground">Book, Slide, Quiz, Vid</p>
        </div>
        <div className="flex flex-col items-center rounded-lg border bg-card p-4 text-center">
          <div className="mb-3 rounded-full bg-primary/10 p-2">
            <BookOpen className="h-5 w-5 text-primary" />
          </div>
          <h3 className="mb-1 text-sm font-semibold">3. Nhận kết quả</h3>
          <p className="text-xs text-muted-foreground">Artifact sẵn sàng để học</p>
        </div>
      </div>

      <div className="mb-8 w-full max-w-2xl">
        <UploadBox onUploaded={handleUploaded} />
      </div>

      {courseId && (
        <Card className="mb-8 w-full max-w-3xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {courseStatus === "ready" ? (
                <CheckCircle2 className="h-4 w-4 text-green-600" />
              ) : courseStatus === "failed" ? (
                <CircleAlert className="h-4 w-4 text-destructive" />
              ) : (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              )}
              {statusLabel}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-muted-foreground">
            <p>ID tài liệu: {courseId}</p>
            <p>File: {filename}</p>
            {isPolling && <p>Backend đang phân tích tài liệu...</p>}
          </CardContent>
        </Card>
      )}

      <div className="mb-8 w-full max-w-3xl">
        <FeatureSelector selected={selectedFeature} onSelect={setSelectedFeature} />
      </div>

      <div className="mb-8 w-full max-w-3xl">
        <PromptInput
          onSubmit={handlePromptSubmit}
          isLoading={isProcessing}
          disabled={!selectedFeature || !courseId || courseStatus !== "ready"}
        />
      </div>

      {result && selectedFeature && (
        <ResultRenderer
          feature={selectedFeature}
          result={result}
        />
      )}
    </div>
  );
}
