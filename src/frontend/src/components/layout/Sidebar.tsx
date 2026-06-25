import Link from "next/link";
import { ScrollArea } from "@/components/ui/scroll-area";

const NAV_ITEMS = [{ href: "/generate", label: "Generate" }];

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-16 z-40 h-[calc(100vh-4rem)] w-64 border-r bg-background p-4">
      <ScrollArea className="h-full">
        <nav className="space-y-2">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </ScrollArea>
    </aside>
  );
}
