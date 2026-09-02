import type { Metadata } from "next";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { UploadZone } from "@/components/course/UploadZone";

export const metadata: Metadata = {
  title: "Mở một không gian học từ tài liệu",
  description:
    "Tải PDF, DOCX hoặc TXT. Bạn có thể tạo từng loại học liệu sau khi tệp được đọc và lập chỉ mục.",
};

export default function CreateCoursePage() {
  return (
    <AuthGuard>
      <div className="mx-auto max-w-2xl px-4 py-8 sm:py-12">
        <div className="mb-8">
          <h1 className="font-display text-3xl font-semibold text-foreground sm:text-4xl">
            Mở một không gian học từ tài liệu
          </h1>
          <p className="mt-2 text-muted-foreground">
            Tải PDF, DOCX hoặc TXT. Bạn có thể tạo từng loại học liệu sau khi
            tệp được đọc và lập chỉ mục.
          </p>
        </div>
        <UploadZone />
      </div>
    </AuthGuard>
  );
}
