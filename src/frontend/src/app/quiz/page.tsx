import Link from "next/link";
import { getCoursesAll } from "@/lib/api";
import { Button } from "@/components/ui";

export default async function QuizLandingPage() {
  let courses: Awaited<ReturnType<typeof getCoursesAll>>["courses"] = [];

  try {
    const data = await getCoursesAll();
    courses = data.courses ?? [];
  } catch {
    // API chưa sẵn sàng — render danh sách rỗng
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Làm Quiz
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Chọn tài liệu đã xử lý để tạo bài kiểm tra trắc nghiệm.
        </p>
      </div>

      {courses.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
          <p className="text-sm text-muted-foreground">
            Chưa có tài liệu nào. Hãy upload tài liệu để bắt đầu.
          </p>
          <Link href="/generate">
            <Button className="mt-4">Upload tài liệu</Button>
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((course) => (
            <div
              key={course.course_id}
              className="flex flex-col rounded-lg border border-border bg-card p-4 shadow-sm"
            >
              <div className="flex-1 space-y-2">
                <h3 className="text-sm font-medium text-foreground">
                  Tài liệu {course.course_id.slice(0, 8)}...
                </h3>
                <p className="text-xs text-muted-foreground">
                  Trạng thái:{" "}
                  <span
                    className={
                      course.status === "ready"
                        ? "text-green-600 font-medium"
                        : "text-amber-600 font-medium"
                    }
                  >
                    {course.status}
                  </span>
                </p>
                {course.created_at && (
                  <p className="text-xs text-muted-foreground">
                    Tạo ngày: {course.created_at}
                  </p>
                )}
              </div>
              <div className="mt-4">
                <Link href={`/quiz/${course.course_id}`} className="w-full">
                  <Button
                    className="w-full"
                    disabled={course.status !== "ready"}
                  >
                    {course.status === "ready"
                      ? "Làm quiz"
                      : "Đang xử lý..."}
                  </Button>
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
