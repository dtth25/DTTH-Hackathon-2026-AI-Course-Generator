"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ChevronLeft, Loader2, AlertCircle, Download } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import { generateMindmap, type MindmapResponse } from "@/lib/api";

export default function MindmapPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.id as string;

  const [data, setData] = useState<MindmapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchMindmap() {
      try {
        setLoading(true);
        setError(null);
        const result = await generateMindmap(courseId);
        setData(result);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Không thể tạo mindmap."
        );
      } finally {
        setLoading(false);
      }
    }
    fetchMindmap();
  }, [courseId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Đang tạo mindmap...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-sm text-destructive font-medium">{error}</p>
        <Button variant="outline" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  if (!data || !data.mindmap) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <p className="text-sm text-muted-foreground">Chưa có mindmap.</p>
        <Button variant="outline" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  const { mindmap } = data;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Quay lại
        </button>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">
            🧠 Mind Map
          </h1>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const blob = new Blob(
                [JSON.stringify(data, null, 2)],
                { type: "application/json" }
              );
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `mindmap_${courseId}.json`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download className="h-4 w-4 mr-1" />
            Tải JSON
          </Button>
        </div>
      </div>

      {/* Central topic */}
      <Card className="bg-primary/5 border-primary/20">
        <CardContent className="p-6 text-center">
          <h2 className="text-xl font-bold text-primary">
            {mindmap.central_topic || "Chủ đề trung tâm"}
          </h2>
        </CardContent>
      </Card>

      {/* Branches */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {mindmap.branches?.map((branch, idx) => (
          <Card key={idx} className="hover:shadow-md transition-shadow">
            <CardContent className="p-4 space-y-3">
              <h3 className="font-semibold text-base">{branch.title}</h3>
              {branch.children && branch.children.length > 0 && (
                <ul className="space-y-1.5">
                  {branch.children.map((child, childIdx) => (
                    <li
                      key={childIdx}
                      className="text-sm text-muted-foreground flex items-start gap-2"
                    >
                      <span className="text-primary mt-1 shrink-0">●</span>
                      <span>{typeof child === "string" ? child : child.title || child}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Citations */}
      {data.citations && data.citations.length > 0 && (
        <div className="border-t pt-4 mt-8">
          <h3 className="text-sm font-medium mb-2">📖 Trích dẫn</h3>
          <div className="flex flex-wrap gap-2">
            {data.citations.slice(0, 5).map((c, idx) => (
              <span
                key={idx}
                className="text-xs bg-muted px-2 py-1 rounded-md"
              >
                Trang {c.page} — {c.source}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}