'use client';

import AppThemeProvider from './theme-provider';
import CourseBuilder from './course-builder';

export default function ClientShell() {
  return (
    <AppThemeProvider>
      <CourseBuilder />
    </AppThemeProvider>
  );
}
