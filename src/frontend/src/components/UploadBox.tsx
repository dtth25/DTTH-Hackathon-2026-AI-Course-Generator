"use client";

import React, { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { UploadCloud, FileText, FileWarning, Trash2, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { validateFiles, ALLOWED_MIME_TYPES, MAX_FILE_SIZE } from "@/lib/validation";
import { type UploadResponse, uploadFile } from "@/lib/api";

const ACCEPTED_TYPES: Record<string, string[]> = {};
for (const mime of ALLOWED_MIME_TYPES) {
  ACCEPTED_TYPES[mime] = [];
}

type UploadStatus = "idle" | "uploading" | "success" | "error";

interface FileItem {
  file: File;
  status: UploadStatus;
  progress: number;
  error?: string;
}

interface UploadBoxProps {
  onUploaded?: (result: UploadResponse) => void;
}

export default function UploadBox({ onUploaded }: UploadBoxProps) {
  const [fileItems, setFileItems] = useState<FileItem[]>([]);

  const updateFileStatus = (fileName: string, updates: Partial<FileItem>) => {
    setFileItems((prev) =>
      prev.map((item) =>
        item.file.name === fileName ? { ...item, ...updates } : item
      )
    );
  };

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const { validFiles, errors } = validateFiles(acceptedFiles);

    // Show all validation errors as toasts
    errors.forEach((errMsg) => toast.error(errMsg));

    if (validFiles.length > 0) {
      const [file] = validFiles;
      const newItem: FileItem = {
        file,
        status: "idle" as UploadStatus,
        progress: 0,
      };
      setFileItems([newItem]);
      toast.success(`Đã chọn "${file.name}"`);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: MAX_FILE_SIZE,
    maxFiles: 1,
    multiple: false,
  });

  const handleRemoveFile = (fileName: string) => {
    setFileItems((prev) => prev.filter((item) => item.file.name !== fileName));
  };

  const handleUpload = async () => {
    const filesToUpload = fileItems.filter((item) => item.status !== "success");
    if (filesToUpload.length === 0) {
      toast.error("Không có file nào để tải lên");
      return;
    }

    // Mark all as uploading
    filesToUpload.forEach((item) => {
      updateFileStatus(item.file.name, { status: "uploading", progress: 0 });
    });

    try {
      // Simulate upload progress with a progress bar
      const simulateProgress = () => {
        let totalProgress = 0;
        const interval = setInterval(() => {
          totalProgress += Math.random() * 15;
          if (totalProgress >= 90) {
            totalProgress = 90;
            clearInterval(interval);
          }
          filesToUpload.forEach((item) => {
            updateFileStatus(item.file.name, { progress: Math.round(totalProgress) });
          });
        }, 300);
        return interval;
      };

      const progressInterval = simulateProgress();

      const result = await uploadFile(filesToUpload[0].file);

      clearInterval(progressInterval);

      // Mark all as success
      filesToUpload.forEach((item) => {
        updateFileStatus(item.file.name, { status: "success", progress: 100 });
      });

      toast.success("Tải lên thành công! Tài liệu đang được xử lý...");
      onUploaded?.(result);

      // Optionally clear the list after success
      // setFileItems([]);

      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Có lỗi xảy ra khi tải lên";
      filesToUpload.forEach((item) => {
        updateFileStatus(item.file.name, {
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
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "error":
        return <FileWarning className="h-4 w-4 text-red-500" />;
      default:
        return <FileText className="h-5 w-5 mr-3 text-gray-500 shrink-0" />;
    }
  };

  const hasFilesToUpload = fileItems.some((item) => item.status !== "success");

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle className="text-center">Tải lên tài liệu của bạn</CardTitle>
        <p className="text-sm text-muted-foreground text-center">
          Hỗ trợ PDF, DOCX, TXT. Tối đa 50MB mỗi file.
        </p>
      </CardHeader>
      <CardContent>
        {/* Dropzone Area */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors
            ${isDragActive
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:border-muted-foreground/50 hover:bg-muted/50"
            }`}
        >
          <Input {...getInputProps()} />
          <UploadCloud
            className={`mx-auto h-12 w-12 mb-4 transition-colors ${
              isDragActive ? "text-primary" : "text-muted-foreground"
            }`}
          />
          {isDragActive ? (
            <p className="text-lg font-medium text-primary">Thả file vào đây...</p>
          ) : (
            <>
              <p className="text-lg text-muted-foreground">
                Kéo thả file PDF, DOCX, TXT vào đây hoặc{" "}
                <span className="text-primary font-medium">click để chọn file</span>
              </p>
            </>
          )}
        </div>

        {/* File list */}
        {fileItems.length > 0 && (
          <div className="mt-6">
            <h3 className="text-md font-semibold mb-3">
              File đã chọn
            </h3>
            <ul className="space-y-2">
              {fileItems.map((item, index) => (
                <li
                  key={`${item.file.name}-${index}`}
                  className={`flex flex-col p-3 border rounded-md ${
                    item.status === "error"
                      ? "bg-destructive/5 border-destructive/30"
                      : item.status === "success"
                      ? "bg-green-50 border-green-200"
                      : "bg-muted/30"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center min-w-0 flex-1">
                      {getStatusIcon(item.status)}
                      <span className="text-sm truncate ml-2">{item.file.name}</span>
                      <span className="text-xs text-muted-foreground ml-2 shrink-0">
                        ({(item.file.size / (1024 * 1024)).toFixed(1)} MB)
                      </span>
                    </div>
                    {item.status === "idle" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveFile(item.file.name)}
                        className="text-destructive hover:bg-destructive/10 ml-2 shrink-0"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>

                  {/* Progress bar for uploading */}
                  {item.status === "uploading" && (
                    <div className="mt-2">
                      <Progress value={item.progress} className="h-1.5" />
                      <p className="text-xs text-muted-foreground mt-1">
                        Đang tải lên... {item.progress}%
                      </p>
                    </div>
                  )}

                  {/* Error message */}
                  {item.status === "error" && item.error && (
                    <p className="text-xs text-destructive mt-1">{item.error}</p>
                  )}

                  {/* Success message */}
                  {item.status === "success" && (
                    <p className="text-xs text-green-600 mt-1">Đã tải lên thành công</p>
                  )}
                </li>
              ))}
            </ul>

            {/* Upload button */}
            {hasFilesToUpload && (
              <Button
                onClick={handleUpload}
                className="w-full mt-6"
                size="lg"
                disabled={fileItems.some((item) => item.status === "uploading")}
              >
                {fileItems.some((item) => item.status === "uploading") ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Đang tải lên...
                  </>
                ) : (
                  <>
                    <UploadCloud className="mr-2 h-4 w-4" />
                    Tải lên và Tạo nội dung
                  </>
                )}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
