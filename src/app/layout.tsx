import type { Metadata } from "next";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import "@/styles/globals.css";

const dmSans = DM_Sans({ 
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TaniejJedz.pl - Porównaj ceny dostaw jedzenia",
  description: "Porównaj ceny dostaw z Pyszne.pl, Uber Eats, Wolt i Glovo w Twojej okolicy. Sprawdź, gdzie zamówisz najtaniej i zaoszczędź na jedzeniu.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pl" className={`${dmSans.variable} ${jetBrainsMono.variable}`}>
      <body className="antialiased min-h-screen flex flex-col">
        {/* Toast container will be injected here in later phases */}
        <main className="flex-grow">
          {children}
        </main>
      </body>
    </html>
  );
}