import type { Metadata } from 'next';
import { DM_Sans } from 'next/font/google';
import { ToastProvider } from '@/components/ui/Toast';
import QueryProvider from '@/lib/query-provider';
import './globals.css';

const dmSans = DM_Sans({
  subsets: ['latin', 'latin-ext'],
  weight: ['400', '500', '600'],
  display: 'swap',
  variable: '--font-sans',
});

export const metadata: Metadata = {
  title: {
    default: 'TaniejJedz.pl — Porównaj ceny dostaw jedzenia',
    template: '%s | TaniejJedz.pl',
  },
  description:
    'Porównaj ceny dostaw jedzenia w Twojej okolicy. Sprawdzamy Pyszne.pl, Uber Eats, Wolt i Glovo — żebyś płacił mniej.',
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'),
  openGraph: {
    type: 'website',
    locale: 'pl_PL',
    siteName: 'TaniejJedz.pl',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pl" className={dmSans.variable}>
      <body className="min-h-screen font-sans">
        <QueryProvider>
          <ToastProvider>{children}</ToastProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
