'use client';

import { Plus } from 'lucide-react';

interface AddToCartButtonProps {
  onClick: () => void;
  isExpanded: boolean;
}

export default function AddToCartButton({ onClick, isExpanded }: AddToCartButtonProps) {
  return (
    <button
      onClick={onClick}
      className={[
        'shrink-0 w-8 h-8 flex items-center justify-center',
        'rounded-sm border transition-colors duration-fast',
        isExpanded
          ? 'bg-primary border-primary text-text-inverse'
          : 'border-border text-text-secondary hover:border-primary hover:text-primary hover:bg-primary-light',
      ].join(' ')}
      aria-label={isExpanded ? 'Zamknij konfigurację' : 'Dodaj do koszyka'}
      aria-expanded={isExpanded}
    >
      <Plus
        size={16}
        className={`transition-transform duration-fast ${isExpanded ? 'rotate-45' : ''}`}
      />
    </button>
  );
}
