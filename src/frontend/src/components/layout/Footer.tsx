import { BrandMark } from "@/components/brand/BrandMark";
import { CONTAINER_WIDE } from "@/lib/layout";
import { cn } from "@/lib/utils";

export function Footer() {
  return (
    <footer className="border-t bg-background">
      <div
        className={cn(
          CONTAINER_WIDE,
          "flex flex-col gap-5 py-8 text-sm text-muted-foreground sm:flex-row sm:items-end sm:justify-between"
        )}
      >
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-foreground">
            <BrandMark className="text-primary" />
            <span className="font-display text-lg font-semibold">HackaGen</span>
          </div>
          <p>Học liệu bắt đầu từ tài liệu của bạn.</p>
        </div>
        <p>© {new Date().getFullYear()} HackaGen</p>
      </div>
    </footer>
  );
}
