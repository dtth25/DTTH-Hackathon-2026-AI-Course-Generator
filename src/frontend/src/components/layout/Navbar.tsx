import Link from "next/link";

export function Navbar() {
  return (
    <nav className="fixed top-0 z-50 flex h-16 w-full items-center border-b bg-background/85 px-4 backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between">
        <Link href="/generate" className="text-lg font-bold">
          AI Course Generator
        </Link>
        <Link
          href="/generate"
          className="rounded-md border px-3 py-2 text-sm font-medium hover:bg-muted"
        >
          Tạo học liệu
        </Link>
      </div>
    </nav>
  );
}
