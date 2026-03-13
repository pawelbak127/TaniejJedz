import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="w-full border-t border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="mx-auto max-w-[1280px] px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-2">
        <p className="text-[var(--text-sm)] text-[var(--color-text-tertiary)]">
          &copy; {new Date().getFullYear()} TaniejJedz.pl
        </p>
        <Link
          href="/polityka-prywatnosci"
          className="text-[var(--text-sm)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors duration-[var(--transition-fast)]"
        >
          Polityka prywatności
        </Link>
      </div>
    </footer>
  );
}
