import './globals.css';

export const metadata = {
  title: 'StudyHack.AI Course Compiler v5.4',
  description: 'Upload PDF and generate a maintainable academic course with polished university-style UI.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
