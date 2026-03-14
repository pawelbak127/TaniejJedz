import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="w-full border-t border-border bg-surface">
      <div className="mx-auto max-w-[1280px] px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-2">
        <p className="text-sm text-text-tertiary">
          &copy; {new Date().getFullYear()} TaniejJedz.pl
        </p>
        <Link
          href="/polityka-prywatnosci"
          className="text-sm text-text-tertiary hover:text-text-secondary transition-colors duration-fast"
        >
          Polityka prywatności
        </Link>
      </div>
    </footer>
  );
}
