"use client"

import { useState, useEffect } from "react"
import type { Course } from "@/types/course"

interface UseCourseReturn {
  course: Course | null
  loading: boolean
  error: string | null
}

export function useCourse(fileId: string | undefined): UseCourseReturn {
  const [course, setCourse] = useState<Course | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!fileId) {
      setError("Missing file ID")
      setLoading(false)
      return
    }

    const fetchCourse = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`/api/generate-course`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file_id: fileId, user_prompt: "" }),
        })

        if (!res.ok) {
          throw new Error(`API error: ${res.status} ${res.statusText}`)
        }

        const data: Course = await res.json()
        setCourse(data)
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Không thể tải khóa học"
        )
      } finally {
        setLoading(false)
      }
    }

    fetchCourse()
  }, [fileId])

  return { course, loading, error }
}