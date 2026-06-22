import { Button } from "@/components/ui";
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
            Upload tài liệu và để AI tự động tạo khóa học, bài học, tóm tắt,
            flashcard, quiz, slide và mind map.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Bắt đầu ngay</CardTitle>
            <CardDescription>
              Bạn chỉ cần upload file và chọn một tính năng bên dưới để bắt đầu
              tạo nội dung học tập.
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex flex-wrap gap-3">
            <Button>Upload tài liệu</Button>
            <Button variant="outline">Tạo khóa học</Button>
            <Button variant="secondary">Tóm tắt</Button>
            <Button variant="ghost">Flashcard</Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
