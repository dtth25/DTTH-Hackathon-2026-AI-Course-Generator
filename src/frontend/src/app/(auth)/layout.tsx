import Link from "next/link";
import { BrandMark } from "@/components/brand/BrandMark";

export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="min-h-screen flex">
      <div className="hidden bg-secondary p-8 text-secondary-foreground md:flex md:w-[35%] md:flex-col md:items-start md:justify-center lg:w-[30%] lg:p-10">
        <Link href="/" className="mb-8 flex items-center gap-3 text-foreground">
          <BrandMark size={36} className="text-primary" />
          <span className="font-display text-2xl font-semibold">HackaGen</span>
        </Link>
        <p className="max-w-xs font-display text-2xl leading-snug text-foreground lg:text-3xl">
          Mang theo tài liệu. HackaGen giúp bạn sắp lại thành một buổi học có thể dùng tiếp.
        </p>
        <div aria-hidden="true" className="my-8 h-px w-full max-w-xs bg-border" />
        <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">
          PDF · DOCX · TXT
        </p>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-8">
        <div className="w-full max-w-md">
          <div className="md:hidden flex items-center justify-center gap-2 mb-8">
            <Link
              href="/"
              className="flex items-center gap-2 text-foreground"
            >
              <BrandMark size={32} className="text-primary" />
              <span className="font-display text-xl font-semibold">HackaGen</span>
            </Link>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
