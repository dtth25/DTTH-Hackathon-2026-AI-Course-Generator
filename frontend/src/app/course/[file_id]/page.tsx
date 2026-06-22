import { CourseView } from "@/components/course/CourseView"

interface CoursePageProps {
  params: {
    file_id: string
  }
}

export default function CoursePage({ params }: CoursePageProps) {
  return (
    <main className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <CourseView fileId={params.file_id} />
      </div>
    </main>
  )
}