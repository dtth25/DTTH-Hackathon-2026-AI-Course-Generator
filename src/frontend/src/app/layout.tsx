import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { MainContent } from "@/components/layout/MainContent";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Course Generator",
  description:
    "Upload tài liệu (PDF, DOCX, TXT) và tạo đúng 4 output học tập: Book, Slide, Quiz và Vid.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body
        className={`${geistSans.variable} ${geistMono.variable} min-h-full flex flex-col bg-background text-foreground`}
      >
        <Navbar />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <MainContent>{children}</MainContent>
        </div>
        <Toaster richColors position="bottom-right" />
      </body>
    </html>
  );
}
