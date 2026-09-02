"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { Menu, X, LogOut, Plus, UserRound } from "lucide-react";
import { BrandMark } from "@/components/brand/BrandMark";
import { Button, buttonVariants } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { isAuthenticated, removeToken } from "@/lib/auth";
import { apiLogout } from "@/lib/api";
import { CONTAINER_WIDE } from "@/lib/layout";
import { cn } from "@/lib/utils";

export function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    let mounted = true;
    Promise.resolve().then(() => {
      if (mounted) {
        setAuthed(isAuthenticated());
      }
    });
    return () => {
      mounted = false;
    };
  }, [pathname]);

  const handleLogout = async () => {
    await apiLogout();
    removeToken();
    setAuthed(false);
    router.push("/login");
  };

  if (pathname.startsWith("/login") || pathname.startsWith("/register")) {
    return null;
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background">
      <div className={cn(CONTAINER_WIDE, "flex h-16 items-center justify-between")}>
        <Link
          href="/"
          className="flex items-center gap-2 text-foreground transition-opacity hover:opacity-80"
        >
          <BrandMark className="text-primary" />
          <span className="font-display text-lg font-semibold">HackaGen</span>
        </Link>

        <nav className="hidden md:flex items-center gap-2">
          <ThemeToggle />
          {authed ? (
            <>
              <Link
                href="/courses"
                className={buttonVariants({
                  variant: "ghost",
                  size: "sm",
                  className: pathname === "/courses" ? "bg-accent" : "",
                })}
              >
                Khóa học của tôi
              </Link>
              <Link
                href="/courses/create"
                className={buttonVariants({
                  variant: "default",
                  size: "sm",
                })}
              >
                <Plus className="mr-1 h-4 w-4" />
                Tạo mới
              </Link>
              <Link
                href="/account"
                className={buttonVariants({
                  variant: "ghost",
                  size: "sm",
                  className: pathname === "/account" ? "bg-accent" : "",
                })}
              >
                <UserRound className="mr-1 h-4 w-4" />
                Tài khoản
              </Link>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="mr-1 h-4 w-4" />
                Đăng xuất
              </Button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className={buttonVariants({
                  variant: "ghost",
                  size: "sm",
                })}
              >
                Đăng nhập
              </Link>
              <Link
                href="/register"
                className={buttonVariants({
                  variant: "default",
                  size: "sm",
                })}
              >
                Bắt đầu
              </Link>
            </>
          )}
        </nav>

        <div className="flex items-center gap-1 md:hidden">
          <ThemeToggle />
          <button
            type="button"
            className="p-2 rounded-md hover:bg-accent"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? "Đóng trình đơn" : "Mở trình đơn"}
            aria-expanded={mobileOpen}
            aria-controls="mobile-navigation"
          >
            {mobileOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <nav
          id="mobile-navigation"
          aria-label="Điều hướng di động"
          className="md:hidden border-t bg-background px-4 py-3 space-y-2"
        >
          {authed ? (
            <>
              <Link
                href="/courses"
                className="block rounded-md px-3 py-2 text-sm hover:bg-accent"
                onClick={() => setMobileOpen(false)}
              >
                Khóa học của tôi
              </Link>
              <Link
                href="/courses/create"
                className="block rounded-md px-3 py-2 text-sm hover:bg-accent"
                onClick={() => setMobileOpen(false)}
              >
                Tạo mới
              </Link>
              <Link
                href="/account"
                className="block rounded-md px-3 py-2 text-sm hover:bg-accent"
                onClick={() => setMobileOpen(false)}
              >
                Tài khoản
              </Link>
              <button
                className="block w-full text-left rounded-md px-3 py-2 text-sm hover:bg-accent text-destructive"
                onClick={handleLogout}
              >
                Đăng xuất
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="block rounded-md px-3 py-2 text-sm hover:bg-accent"
                onClick={() => setMobileOpen(false)}
              >
                Đăng nhập
              </Link>
              <Link
                href="/register"
                className="block rounded-md px-3 py-2 text-sm font-medium text-primary hover:bg-accent"
                onClick={() => setMobileOpen(false)}
              >
                Bắt đầu
              </Link>
            </>
          )}
        </nav>
      )}
    </header>
  );
}
