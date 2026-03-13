'use client';

import { ChevronDown } from 'lucide-react';

interface RestaurantFiltersProps {
  cuisines: string[];
  activeCuisines: string[];
  onCuisineToggle: (cuisine: string) => void;
  sortBy: 'relevance' | 'cheapest_delivery' | 'rating';
  onSortChange: (sort: 'relevance' | 'cheapest_delivery' | 'rating') => void;
  showClosed: boolean;
  onShowClosedChange: (show: boolean) => void;
}

const SORT_LABELS: Record<string, string> = {
  relevance: 'Trafność',
  cheapest_delivery: 'Najtańsza dostawa',
  rating: 'Ocena',
};

export default function RestaurantFilters({
  cuisines,
  activeCuisines,
  onCuisineToggle,
  sortBy,
  onSortChange,
  showClosed,
  onShowClosedChange,
}: RestaurantFiltersProps) {
  return (
    <div className="flex flex-col gap-3">
      {/* Cuisine pills + sort row */}
      <div className="flex items-center gap-3">
        {/* Cuisine pills — scrollable */}
        <div className="flex-1 overflow-x-auto scrollbar-hide">
          <div className="flex items-center gap-2 pb-0.5">
            <CuisinePill
              label="Wszystkie"
              isActive={activeCuisines.length === 0}
              onClick={() => {
                if (activeCuisines.length > 0) {
                  // Clear all — parent handles
                  activeCuisines.forEach((c) => onCuisineToggle(c));
                }
              }}
            />
            {cuisines.map((cuisine) => (
              <CuisinePill
                key={cuisine}
                label={capitalizeFirst(cuisine)}
                isActive={activeCuisines.includes(cuisine)}
                onClick={() => onCuisineToggle(cuisine)}
              />
            ))}
          </div>
        </div>

        {/* Sort dropdown */}
        <div className="shrink-0 relative">
          <label htmlFor="sort-select" className="sr-only">
            Sortuj
          </label>
          <select
            id="sort-select"
            value={sortBy}
            onChange={(e) =>
              onSortChange(e.target.value as 'relevance' | 'cheapest_delivery' | 'rating')
            }
            className={[
              'appearance-none',
              'h-8 pl-3 pr-8',
              'text-[var(--text-sm)] font-medium',
              'bg-[var(--color-surface)]',
              'border border-[var(--color-border)] rounded-[var(--radius-sm)]',
              'text-[var(--color-text-secondary)]',
              'hover:border-[var(--color-border-strong)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]',
              'cursor-pointer',
              'transition-colors duration-[var(--transition-fast)]',
            ].join(' ')}
          >
            {Object.entries(SORT_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--color-text-tertiary)]"
            aria-hidden="true"
          />
        </div>
      </div>

      {/* "Open only" checkbox */}
      <label className="inline-flex items-center gap-2 cursor-pointer self-start">
        <input
          type="checkbox"
          checked={!showClosed}
          onChange={(e) => onShowClosedChange(!e.target.checked)}
          className="w-4 h-4 rounded-[3px] border-[var(--color-border-strong)] text-[var(--color-primary)] focus:ring-[var(--color-primary)]/30 focus:ring-2 cursor-pointer accent-[var(--color-primary)]"
        />
        <span className="text-[var(--text-sm)] text-[var(--color-text-secondary)] select-none">
          Tylko otwarte
        </span>
      </label>
    </div>
  );
}

function CuisinePill({
  label,
  isActive,
  onClick,
}: {
  label: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'shrink-0 h-8 px-3.5',
        'rounded-[var(--radius-full)]',
        'text-[var(--text-sm)] font-medium whitespace-nowrap',
        'transition-colors duration-[var(--transition-fast)]',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]',
        isActive
          ? 'bg-[var(--color-primary)] text-[var(--color-text-inverse)]'
          : 'bg-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border-strong)]',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function capitalizeFirst(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
