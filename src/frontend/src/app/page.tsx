import Link from "next/link";
import { BookOpen, ClipboardCheck, FileVideo, Presentation } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import { cn } from "@/lib/utils";

const OUTPUTS = [
  {
    label: "Book",
    description: "Đọc theo chương, bài học và mục tiêu rõ ràng.",
    icon: BookOpen,
  },
  {
    label: "Slide",
    description: "Trình chiếu từng trang, có điều hướng và tải xuống.",
    icon: Presentation,
  },
  {
    label: "Quiz",
    description: "Làm trắc nghiệm, nộp bài và xem điểm.",
    icon: ClipboardCheck,
  },
  {
    label: "Vid",
    description: "Video học tập dạng slide kèm voiceover.",
    icon: FileVideo,
  },
];

export default function Home() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-12">
      <section className="grid flex-1 gap-8 lg:grid-cols-[1fr_420px] lg:items-center">
        <div className="space-y-6">
          <div className="inline-flex rounded-md border bg-card px-3 py-2 text-sm text-muted-foreground">
            Không cần tài khoản · Chỉ tập trung vào học liệu
          </div>
          <div className="space-y-4">
            <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
              Tạo Book, Slide, Quiz và Vid từ tài liệu của bạn
            </h1>
            <p className="max-w-2xl text-base leading-7 text-muted-foreground">
              Upload một hoặc nhiều tài liệu PDF, DOCX, TXT rồi tạo đủ bốn output
              học tập trong cùng một workspace.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/generate"
              className={buttonVariants({ variant: "default", size: "lg" })}
            >
              Bắt đầu tạo học liệu
            </Link>
            <Link
              href="/generate"
              className={buttonVariants({ variant: "outline", size: "lg" })}
            >
              Mở workspace
            </Link>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>4 output chính</CardTitle>
            <CardDescription>
              Mỗi output có renderer riêng và có thể tải artifact sau khi tạo.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {OUTPUTS.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.label}
                  href="/generate"
                  className={cn(
                    "flex items-start gap-3 rounded-lg border p-4 transition-colors",
                    "hover:border-primary/40 hover:bg-muted/50"
                  )}
                >
                  <span className="rounded-md bg-muted p-2 text-muted-foreground">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span>
                    <span className="block font-semibold">{item.label}</span>
                    <span className="mt-1 block text-sm leading-6 text-muted-foreground">
                      {item.description}
                    </span>
                  </span>
                </Link>
              );
            })}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
