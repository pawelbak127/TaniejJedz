'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { MapPin } from 'lucide-react';
import { useAddress } from '@/hooks/useAddress';

interface HeaderProps {
  showAddress?: boolean;
}

export default function Header({ showAddress = false }: HeaderProps) {
  const { address, removeAddress } = useAddress();
  const router = useRouter();

  const handleChangeAddress = () => {
    removeAddress();
    router.push('/');
  };

  return (
    <header className="w-full border-b border-border bg-surface">
      <div className="mx-auto max-w-[1280px] px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link
          href="/"
          className="flex items-center gap-1.5 text-lg font-semibold text-text-primary hover:text-primary transition-colors duration-fast"
        >
          <span
            className="inline-flex items-center justify-center w-7 h-7 rounded-sm text-sm font-semibold text-text-inverse bg-primary"
            aria-hidden="true"
          >
            T
          </span>
          <span>
            Taniej<span className="text-primary">Jedz</span>
          </span>
        </Link>

        {showAddress && address && (
          <div className="flex items-center gap-2 text-sm">
            <MapPin size={14} className="text-primary shrink-0" aria-hidden="true" />
            <span className="text-text-secondary hidden sm:inline truncate max-w-[240px]">
              {address.formatted}
            </span>
            <button
              onClick={handleChangeAddress}
              className="text-primary font-medium hover:text-primary-hover transition-colors duration-fast whitespace-nowrap"
            >
              zmień
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
