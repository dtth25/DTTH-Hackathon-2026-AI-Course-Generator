"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useDropzone, type FileRejection } from "react-dropzone";
import { Upload, X, FileText, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { apiUploadFiles } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACCEPTED_TYPES: Record<string, string[]> = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
    ".docx",
  ],
  "text/plain": [".txt"],
};
const MAX_SIZE = 50 * 1024 * 1024;
const MAX_FILES = 5;

export function UploadZone() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    (
      accepted: File[],
      rejected: FileRejection[]
    ) => {
      setError(null);
      if (rejected.length > 0) {
        const first = rejected[0];
        const code = first.errors[0]?.code;
        if (code === "file-too-large") {
          setError("File quá lớn. Kích thước tối đa là 50MB.");
        } else if (code === "file-invalid-type") {
          setError(
            "Định dạng không được hỗ trợ. Chỉ chấp nhận PDF, DOCX, TXT."
          );
        } else {
          setError("File không hợp lệ.");
        }
        return;
      }
      setFiles((prev) => {
        const names = new Set(prev.map((f) => f.name));
        const newFiles = accepted.filter((f) => !names.has(f.name));
        const combined = [...prev, ...newFiles];
        if (combined.length > MAX_FILES) {
          setError(`Chỉ được phép tải lên tối đa ${MAX_FILES} file mỗi lần.`);
        }
        return combined.slice(0, MAX_FILES);
      });
    },
    []
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: MAX_SIZE,
    multiple: true,
  });

  const removeFile = (name: string) => {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setProgress(0);
    setError(null);
    try {
      const result = await apiUploadFiles(files, setProgress);
      router.push("/course/" + result.course_id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Upload thất bại. Vui lòng thử lại."
      );
    } finally {
      setUploading(false);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      <div
        {...getRootProps()}
        className={cn(
          "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50 hover:bg-muted/50"
        )}
      >
        <input {...getInputProps()} />
        <Upload
          className={cn(
            "h-12 w-12 mb-4",
            isDragActive ? "text-primary" : "text-muted-foreground"
          )}
        />
        <p className="text-base font-medium">
          {isDragActive
            ? "Thả file vào đây"
            : "Kéo thả file hoặc nhấn để chọn"}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          Hỗ trợ PDF, DOCX, TXT. Tối đa 50MB mỗi file, tối đa {MAX_FILES} file.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {files.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-foreground">
            File đã chọn ({files.length})
          </h3>
          {files.map((file) => (
            <div
              key={file.name}
              className="flex items-center justify-between rounded-lg border bg-background px-4 py-2.5"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileText className="h-4 w-4 shrink-0 text-primary" />
                <span className="text-sm truncate">{file.name}</span>
                <span className="text-xs text-muted-foreground shrink-0">
                  ({formatSize(file.size)})
                </span>
              </div>
              <button
                onClick={() => removeFile(file.name)}
                className="p-1 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                disabled={uploading}
                aria-label={`Xóa ${file.name}`}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {uploading && (
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Đang tải lên...</span>
            <span className="font-medium">{progress}%</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>
      )}

      <Button
        onClick={handleUpload}
        disabled={files.length === 0 || uploading}
        className="w-full"
        size="lg"
      >
        {uploading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Đang xử lý...
          </>
        ) : (
          <>
            <Upload className="mr-2 h-4 w-4" />
            Tải lên {files.length > 0 ? `(${files.length} file)` : ""}
          </>
        )}
      </Button>
    </div>
  );
}
