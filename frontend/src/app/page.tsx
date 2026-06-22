import Link from "next/link"

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-blue-50 to-white">
      <div className="max-w-4xl mx-auto py-16 px-4">
        <div className="text-center space-y-6">
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
            AI Course Generator
          </h1>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Biến tài liệu thô (PDF, DOCX, TXT) thành hệ sinh thái học tập đa phương tiện
          </p>
          <div className="flex justify-center gap-4">
            <Link
              href="/course/demo-file-id"
              className="inline-flex items-center px-6 py-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 transition-colors"
            >
              Xem khóa học mẫu
            </Link>
          </div>
        </div>
      </div>
    </main>
  )
}