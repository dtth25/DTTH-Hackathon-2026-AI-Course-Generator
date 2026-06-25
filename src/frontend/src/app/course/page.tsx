import Link from "next/link";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter,
} from "@/components/ui";
import { Button } from "@/components/ui";
import { getCoursesAll } from "@/lib/api";

export default async function CourseListPage() {
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
          Tài liệu của tôi
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Danh sách tài liệu đã upload để tạo Book, Slide, Quiz và Vid.
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
          {courses.map((course) => {
            const courseLabel =
              course.status === "ready"
                ? `Tài liệu ${course.course_id.slice(0, 8)}...`
                : `Tài liệu ${course.course_id.slice(0, 8)}... (${
                    course.status === "processing" ? "đang xử lý" : course.status
                  })`;

            return (
              <Card key={course.course_id} className="flex flex-col">
                <CardHeader>
                  <CardTitle className="text-lg">{courseLabel}</CardTitle>
                  {course.created_at && (
                    <CardDescription>
                      Tạo ngày: {course.created_at}
                    </CardDescription>
                  )}
                  <CardDescription className="text-xs">
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
                  </CardDescription>
                </CardHeader>
                <CardFooter className="mt-auto">
                  <Link
                    href={`/course/${course.course_id}`}
                    className="w-full"
                  >
                    <Button className="w-full">Mở Book</Button>
                  </Link>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
