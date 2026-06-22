import Link from "next/link";
import { ScrollArea } from "@/components/ui/scroll-area";

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-16 z-40 h-[calc(100vh-4rem)] w-64 border-r bg-background p-4">
      <ScrollArea className="h-full">
        <nav className="space-y-2">
          <Link
            href="/generate"
            className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
          >
            Generate Course
          </Link>
          <Link
            href="/course"
            className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
          >
            My Course
          </Link>
          <Link
            href="/mindmap"
            className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
          >
            Mindmap
          </Link>
          <Link
            href="/quiz"
            className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
          >
            Quiz
          </Link>
          <Link
            href="/flashcards"
            className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
          >
            Flashcards
          </Link>
          <Link
            href="/slides"
            className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
          >
            Slides
          </Link>
        </nav>
      </ScrollArea>
    </aside>
  );
}