
interface MainContentProps {
  children: React.ReactNode;
}

export function MainContent({ children }: MainContentProps) {
  return (
    <main className="flex-1 p-4 pt-20 pl-72"> {/* Adjust padding to account for fixed Navbar and Sidebar */}
      {children}
    </main>
  );
}
