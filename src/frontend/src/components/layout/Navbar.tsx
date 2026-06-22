import Link from "next/link";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

export function Navbar() {
  return (
    <nav className="fixed top-0 w-full z-50 bg-background/80 backdrop-blur-sm border-b h-16 flex items-center px-4">
      <div className="container flex items-center justify-between">
        <Link href="/generate" className="text-lg font-bold">
          AI Course Generator
        </Link>
        <div className="flex items-center space-x-4">
          {/* Mock User Avatar */}
          <Avatar>
            <AvatarImage src="https://github.com/shadcn.png" alt="@shadcn" />
            <AvatarFallback>CN</AvatarFallback>
          </Avatar>
        </div>
      </div>
    </nav>
  );
}