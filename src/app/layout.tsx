import type { Metadata } from 'next';
import { DM_Sans, JetBrains_Mono } from 'next/font/google';
import { ToastProvider } from '@/components/ui/Toast';
import './globals.css';

const dmSans = DM_Sans({
  subsets: ['latin', 'latin-ext'],
  weight: ['400', '500', '600'],
  display: 'swap',
  variable: '--font-sans',
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ['latin', 'latin-ext'],
  weight: ['400', '500'],
  display: 'swap',
  variable: '--font-mono',
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
    <html lang="pl" className={`${dmSans.variable} ${jetBrainsMono.variable}`}>
      <body className="min-h-screen font-sans bg-bg text-text-primary antialiased">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}