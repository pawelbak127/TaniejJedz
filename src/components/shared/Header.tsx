'use client';

import Link from 'next/link';
import { MapPin } from 'lucide-react';
import { useAddress } from '@/hooks/useAddress';

interface HeaderProps {
  showAddress?: boolean;
}

export default function Header({ showAddress = false }: HeaderProps) {
  const { address, removeAddress } = useAddress();

  return (
    <header className="w-full border-b border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="mx-auto max-w-[1280px] px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link
          href="/"
          className="flex items-center gap-1.5 text-[var(--text-lg)] font-semibold text-[var(--color-text-primary)] hover:text-[var(--color-primary)] transition-colors duration-[var(--transition-fast)]"
        >
          <span
            className="inline-flex items-center justify-center w-7 h-7 rounded-[var(--radius-sm)] text-[var(--text-sm)] font-semibold text-[var(--color-text-inverse)]"
            style={{ backgroundColor: 'var(--color-primary)' }}
            aria-hidden="true"
          >
            T
          </span>
          <span>
            Taniej<span className="text-[var(--color-primary)]">Jedz</span>
          </span>
        </Link>

        {showAddress && address && (
          <div className="flex items-center gap-2 text-[var(--text-sm)]">
            <MapPin size={14} className="text-[var(--color-primary)] shrink-0" aria-hidden="true" />
            <span className="text-[var(--color-text-secondary)] hidden sm:inline truncate max-w-[240px]">
              {address.formatted}
            </span>
            <button
              onClick={removeAddress}
              className="text-[var(--color-primary)] font-medium hover:text-[var(--color-primary-hover)] transition-colors duration-[var(--transition-fast)] whitespace-nowrap"
            >
              zmień
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
