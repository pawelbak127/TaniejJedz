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
      <div className="flex items-center gap-3">
        <div className="flex-1 overflow-x-auto scrollbar-hide">
          <div className="flex items-center gap-2 pb-0.5">
            <CuisinePill
              label="Wszystkie"
              isActive={activeCuisines.length === 0}
              onClick={() => {
                if (activeCuisines.length > 0) {
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
            className="appearance-none h-8 pl-3 pr-8 text-sm font-medium bg-surface border border-border rounded-sm text-text-secondary hover:border-border-strong focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary cursor-pointer transition-colors duration-fast"
          >
            {Object.entries(SORT_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={14}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-text-tertiary"
            aria-hidden="true"
          />
        </div>
      </div>

      <label className="inline-flex items-center gap-2 cursor-pointer self-start">
        <input
          type="checkbox"
          checked={!showClosed}
          onChange={(e) => onShowClosedChange(!e.target.checked)}
          className="w-4 h-4 rounded-[3px] border-border-strong text-primary focus:ring-primary/30 focus:ring-2 cursor-pointer accent-primary"
        />
        <span className="text-sm text-text-secondary select-none">
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
        'rounded-full',
        'text-sm font-medium whitespace-nowrap',
        'transition-colors duration-fast',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
        isActive
          ? 'bg-primary text-text-inverse'
          : 'bg-border text-text-secondary hover:bg-border-strong',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

function capitalizeFirst(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
