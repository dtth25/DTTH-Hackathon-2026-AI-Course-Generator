interface MainContentProps {
  children: React.ReactNode;
}

export function MainContent({ children }: MainContentProps) {
  return <main className="flex-1 pt-16">{children}</main>;
}
