"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  CheckCircle2,
  FileText,
  FileWarning,
  Loader2,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ALLOWED_MIME_TYPES, MAX_FILE_SIZE, validateFiles } from "@/lib/validation";
import { type UploadResponse, uploadFiles } from "@/lib/api";

const ACCEPTED_TYPES: Record<string, string[]> = {};
for (const mime of ALLOWED_MIME_TYPES) {
  ACCEPTED_TYPES[mime] = [];
}

type UploadStatus = "idle" | "uploading" | "success" | "error";

interface FileItem {
  id: string;
  file: File;
  status: UploadStatus;
  progress: number;
  error?: string;
}

interface UploadBoxProps {
  onUploaded?: (result: UploadResponse) => void;
}

function fileId(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

function DropzoneSkeleton() {
  return (
    <div className="rounded-lg border-2 border-dashed p-8 text-center border-muted-foreground/25">
      <UploadCloud className="mx-auto mb-4 h-11 w-11 text-muted-foreground" />
      <p className="text-base font-medium">
        Kéo thả tài liệu vào đây hoặc click để chọn file
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        Hệ thống sẽ gộp các file thành một bộ tài liệu chung.
      </p>
    </div>
  );
}

interface DropzoneAreaProps {
  fileItems: FileItem[];
  onDrop: (acceptedFiles: File[]) => void;
  isDragActive: boolean;
  getRootProps: <T extends Record<string, unknown>>(props?: T) => Record<string, unknown>;
  getInputProps: <T extends Record<string, unknown>>(props?: T) => Record<string, unknown>;
}

function DropzoneArea({
  fileItems,
  onDrop,
  isDragActive,
  getRootProps,
  getInputProps,
}: DropzoneAreaProps) {
  const [localFileItems, setLocalFileItems] = useState<FileItem[]>(fileItems);

  useEffect(() => {
    setLocalFileItems(fileItems);
  }, [fileItems]);

  const updateFileStatus = (id: string, updates: Partial<FileItem>) => {
    setLocalFileItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...updates } : item))
    );
  };

  const handleRemoveFile = (id: string) => {
    setLocalFileItems((prev) => prev.filter((item) => item.id !== id));
  };

  const handleUpload = async () => {
    const filesToUpload = localFileItems.filter((item) => item.status !== "success");
    if (filesToUpload.length === 0) {
      toast.error("Chưa có file nào để tải lên.");
      return;
    }

    filesToUpload.forEach((item) => {
      updateFileStatus(item.id, { status: "uploading", progress: 0, error: undefined });
    });

    let totalProgress = 0;
    const progressInterval = window.setInterval(() => {
      totalProgress = Math.min(90, totalProgress + Math.random() * 12);
      filesToUpload.forEach((item) => {
        updateFileStatus(item.id, { progress: Math.round(totalProgress) });
      });
      if (totalProgress >= 90) window.clearInterval(progressInterval);
    }, 300);

    try {
      const result = await uploadFiles(filesToUpload.map((item) => item.file));
      window.clearInterval(progressInterval);

      filesToUpload.forEach((item) => {
        updateFileStatus(item.id, { status: "success", progress: 100 });
      });

      toast.success("Tài liệu đã được tải lên. Hệ thống đang phân tích nội dung.");
      return result;
    } catch (err) {
      window.clearInterval(progressInterval);
      const errorMessage =
        err instanceof Error ? err.message : "Có lỗi xảy ra khi tải tài liệu lên.";
      filesToUpload.forEach((item) => {
        updateFileStatus(item.id, {
          status: "error",
          error: errorMessage,
          progress: 0,
        });
      });
      toast.error(errorMessage);
    }
  };

  const getStatusIcon = (status: UploadStatus) => {
    switch (status) {
      case "uploading":
        return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
      case "success":
        return <CheckCircle2 className="h-4 w-4 text-green-600" />;
      case "error":
        return <FileWarning className="h-4 w-4 text-red-500" />;
      default:
        return <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />;
    }
  };

  const hasFilesToUpload = localFileItems.some((item) => item.status !== "success");
  const isUploading = localFileItems.some((item) => item.status === "uploading");

  const rootProps = getRootProps();
  const inputProps = getInputProps();

  return (
    <>
      <div
        {...rootProps}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50 hover:bg-muted/50"
        }`}
      >
        <Input {...inputProps} />
        <UploadCloud
          className={`mx-auto mb-4 h-11 w-11 transition-colors ${
            isDragActive ? "text-primary" : "text-muted-foreground"
          }`}
        />
        <p className="text-base font-medium">
          {isDragActive
            ? "Thả tài liệu vào đây"
            : "Kéo thả tài liệu vào đây hoặc click để chọn file"}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Hệ thống sẽ gộp các file thành một bộ tài liệu chung.
        </p>
      </div>

      {localFileItems.length > 0 && (
        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold">Tài liệu đã chọn</h3>
            <span className="text-xs text-muted-foreground">
              {localFileItems.length} file
            </span>
          </div>

          <ul className="space-y-2">
            {localFileItems.map((item) => (
              <li
                key={item.id}
                className={`rounded-md border p-3 ${
                  item.status === "error"
                    ? "border-destructive/30 bg-destructive/5"
                    : item.status === "success"
                      ? "border-emerald-200 bg-emerald-50"
                      : "bg-muted/30"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    {getStatusIcon(item.status)}
                    <span className="truncate text-sm">{item.file.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {(item.file.size / (1024 * 1024)).toFixed(1)} MB
                    </span>
                  </div>
                  {item.status === "idle" && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleRemoveFile(item.id)}
                      className="text-destructive hover:bg-destructive/10"
                      type="button"
                      aria-label={`Xóa ${item.file.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                {item.status === "uploading" && (
                  <div className="mt-2">
                    <Progress value={item.progress} className="h-1.5" />
                    <p className="mt-1 text-xs text-muted-foreground">
                      Đang tải lên {item.progress}%
                    </p>
                  </div>
                )}

                {item.status === "error" && item.error && (
                  <p className="mt-1 text-xs text-destructive">{item.error}</p>
                )}

                {item.status === "success" && (
                  <p className="mt-1 text-xs text-emerald-700">
                    Đã tải lên thành công
                  </p>
                )}
              </li>
            ))}
          </ul>

          {hasFilesToUpload && (
            <Button
              onClick={handleUpload}
              className="mt-6 w-full"
              size="lg"
              disabled={isUploading}
              type="button"
            >
              {isUploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Đang tải tài liệu
                </>
              ) : (
                <>
                  <UploadCloud className="mr-2 h-4 w-4" />
                  Tải lên {localFileItems.length} file
                </>
              )}
            </Button>
          )}
        </div>
      )}
    </>
  );
}

export default function UploadBox({ onUploaded }: UploadBoxProps) {
  const [mounted, setMounted] = useState(false);
  const [fileItems, setFileItems] = useState<FileItem[]>([]);

  useEffect(() => {
    setMounted(true);
  }, []);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const { validFiles, errors } = validateFiles(acceptedFiles);
    errors.forEach((errMsg) => toast.error(errMsg));

    if (validFiles.length === 0) return;

    setFileItems((prev) => {
      const seen = new Set(prev.map((item) => item.id));
      const nextItems = validFiles
        .filter((file) => !seen.has(fileId(file)))
        .map((file) => ({
          id: fileId(file),
          file,
          status: "idle" as UploadStatus,
          progress: 0,
        }));

      if (nextItems.length === 0) {
        toast.info("Các file này đã có trong danh sách.");
        return prev;
      }

      toast.success(`Đã chọn ${nextItems.length} file.`);
      return [...prev, ...nextItems];
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: MAX_FILE_SIZE,
    multiple: true,
  });

  return (
    <Card className="w-full">
      <CardHeader className="space-y-2">
        <CardTitle className="text-xl">Tải tài liệu học tập</CardTitle>
        <p className="text-sm text-muted-foreground">
          Có thể tải nhiều file PDF, DOCX hoặc TXT. Mỗi file tối đa 50MB.
        </p>
      </CardHeader>
      <CardContent>
        {mounted ? (
          <DropzoneArea
            fileItems={fileItems}
            onDrop={onDrop}
            isDragActive={isDragActive}
            getRootProps={getRootProps}
            getInputProps={getInputProps}
          />
        ) : (
          <DropzoneSkeleton />
        )}
      </CardContent>
    </Card>
  );
}