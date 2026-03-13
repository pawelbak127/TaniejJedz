import type { Metadata } from 'next';
import { ToastProvider } from '@/components/ui/Toast';
import './globals.css';

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
    <html lang="pl">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen font-sans">
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
