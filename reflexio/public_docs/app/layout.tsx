import './global.css';
import { RootProvider } from 'fumadocs-ui/provider';
import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { source } from '@/lib/source';
import { Inter } from 'next/font/google';
import type { ReactNode } from 'react';
import type { Metadata } from 'next';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: {
    template: '%s | Reflexio Docs',
    default: 'Reflexio Docs',
  },
  description: 'Official documentation for Reflexio - A powerful framework for building AI agents with memory and user profiling capabilities',
  icons: '/assets/reflexio_fav.svg',
};

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <RootProvider search={{ options: { api: '/docs/api/search' } }}>
          <DocsLayout
            tree={source.pageTree}
            nav={{
              title: 'Reflexio Docs',
            }}
          >
            {children}
          </DocsLayout>
        </RootProvider>
      </body>
    </html>
  );
}
