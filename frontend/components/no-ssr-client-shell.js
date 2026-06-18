'use client';

import dynamic from 'next/dynamic';

const ClientShell = dynamic(() => import('./client-shell'), {
  ssr: false,
  loading: () => (
    <main style={{ padding: 32, fontFamily: 'Inter, Arial, system-ui, sans-serif' }}>
      Đang tải StudyHack.AI...
    </main>
  ),
});

export default function NoSSRClientShell() {
  return <ClientShell />;
}
