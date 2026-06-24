import { Button } from "@/components/ui";
import Link from "next/link";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-16">
      <div className="w-full max-w-3xl space-y-8">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            AI Course Generator
          </h1>
          <p className="text-base text-muted-foreground">
            Upload tài liệu và tạo đúng 4 output học tập: Book, Slide, Quiz
            và Vid.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Bắt đầu ngay</CardTitle>
            <CardDescription>
              Bạn chỉ cần upload file, chờ backend xử lý tài liệu và chọn output
              muốn tạo.
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex flex-wrap gap-3">
            <Link href="/generate">
              <Button>Upload tài liệu</Button>
            </Link>
            <Button variant="outline">Book</Button>
            <Button variant="secondary">Slide</Button>
            <Button variant="secondary">Quiz</Button>
            <Button variant="ghost">Vid</Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
