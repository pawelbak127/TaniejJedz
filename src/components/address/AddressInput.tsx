'use client';

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Search, MapPin, Loader2 } from 'lucide-react';
import { useAddress } from '@/hooks/useAddress';
import { useDebounce } from '@/hooks/useDebounce';
import { SUPPORTED_CITIES, DEBOUNCE_ADDRESS_MS, MAX_ADDRESS_SUGGESTIONS } from '@/lib/constants';
import type { Address } from '@/generated/api-types';

interface AddressSuggestion {
  formatted: string;
  latitude: number;
  longitude: number;
  city: string;
}

const MOCK_SUGGESTIONS: AddressSuggestion[] = [
  { formatted: 'ul. Marszałkowska 100, Warszawa', latitude: 52.2297, longitude: 21.0122, city: 'warszawa' },
  { formatted: 'ul. Marszałkowska 12, Warszawa', latitude: 52.2315, longitude: 21.0118, city: 'warszawa' },
  { formatted: 'ul. Nowy Świat 42, Warszawa', latitude: 52.2310, longitude: 21.0180, city: 'warszawa' },
  { formatted: 'ul. Chmielna 8, Warszawa', latitude: 52.2325, longitude: 21.0090, city: 'warszawa' },
  { formatted: 'ul. Mokotowska 17, Warszawa', latitude: 52.2205, longitude: 21.0160, city: 'warszawa' },
  { formatted: 'ul. Koszykowa 55, Warszawa', latitude: 52.2220, longitude: 21.0100, city: 'warszawa' },
  { formatted: 'ul. Wilcza 29, Warszawa', latitude: 52.2240, longitude: 21.0130, city: 'warszawa' },
  { formatted: 'ul. Foksal 3, Warszawa', latitude: 52.2315, longitude: 21.0195, city: 'warszawa' },
  { formatted: 'ul. Świętokrzyska 18, Warszawa', latitude: 52.2350, longitude: 21.0120, city: 'warszawa' },
  { formatted: 'ul. Hożna 62, Warszawa', latitude: 52.2230, longitude: 21.0155, city: 'warszawa' },
  { formatted: 'ul. Krakowskie Przedmieście 5, Warszawa', latitude: 52.2400, longitude: 21.0150, city: 'warszawa' },
  { formatted: 'Rynek Główny 1, Kraków', latitude: 50.0617, longitude: 19.9373, city: 'krakow' },
  { formatted: 'ul. Świdnicka 40, Wrocław', latitude: 51.1079, longitude: 17.0385, city: 'wroclaw' },
];

function searchMockSuggestions(query: string): AddressSuggestion[] {
  if (query.trim().length < 2) return [];
  const q = query.toLowerCase();
  return MOCK_SUGGESTIONS
    .filter(s => s.formatted.toLowerCase().includes(q))
    .slice(0, MAX_ADDRESS_SUGGESTIONS);
}

interface AddressInputProps {
  autoFocus?: boolean;
  size?: 'default' | 'large';
}

export default function AddressInput({ autoFocus = false, size = 'default' }: AddressInputProps) {
  const router = useRouter();
  const { saveAddress } = useAddress();

  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const debouncedQuery = useDebounce(query, DEBOUNCE_ADDRESS_MS);

  // Fetch suggestions on debounced query change
  useEffect(() => {
    if (debouncedQuery.trim().length < 2) {
      setSuggestions([]);
      setIsOpen(false);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);

    // Simulate network delay for mock
    const timer = setTimeout(() => {
      const results = searchMockSuggestions(debouncedQuery);
      setSuggestions(results);
      setIsOpen(results.length > 0);
      setActiveIndex(-1);
      setIsLoading(false);
    }, 100);

    return () => clearTimeout(timer);
  }, [debouncedQuery]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const selectAddress = useCallback(
    (suggestion: AddressSuggestion) => {
      const citySlug = suggestion.city.toLowerCase();
      const isSupported = SUPPORTED_CITIES.includes(citySlug as typeof SUPPORTED_CITIES[number]);

      if (!isSupported) {
        setError('Obsługujemy obecnie: Warszawa');
        setIsOpen(false);
        return;
      }

      setError(null);

      const address: Address = {
        formatted: suggestion.formatted,
        latitude: suggestion.latitude,
        longitude: suggestion.longitude,
        city: citySlug,
      };

      saveAddress(address);
      setQuery(suggestion.formatted);
      setIsOpen(false);
      router.push(`/${citySlug}`);
    },
    [saveAddress, router],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || suggestions.length === 0) {
      if (e.key === 'Enter' && suggestions.length === 0 && query.trim().length >= 2) {
        // Re-search and pick first
        const results = searchMockSuggestions(query);
        if (results.length > 0) {
          selectAddress(results[0]);
        }
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActiveIndex(prev => (prev < suggestions.length - 1 ? prev + 1 : 0));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActiveIndex(prev => (prev > 0 ? prev - 1 : suggestions.length - 1));
        break;
      case 'Enter':
        e.preventDefault();
        if (activeIndex >= 0 && activeIndex < suggestions.length) {
          selectAddress(suggestions[activeIndex]);
        } else if (suggestions.length > 0) {
          selectAddress(suggestions[0]);
        }
        break;
      case 'Escape':
        setIsOpen(false);
        setActiveIndex(-1);
        break;
    }
  };

  // Scroll active item into view
  useEffect(() => {
    if (activeIndex >= 0 && listRef.current) {
      const item = listRef.current.children[activeIndex] as HTMLElement;
      item?.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex]);

  const isLarge = size === 'large';

  return (
    <div ref={containerRef} className="relative w-full">
      <div className="relative">
        <span
          className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] pointer-events-none"
          aria-hidden="true"
        >
          <Search size={isLarge ? 20 : 18} />
        </span>

        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setError(null);
          }}
          onFocus={() => {
            if (suggestions.length > 0) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Wpisz adres dostawy..."
          autoFocus={autoFocus}
          autoComplete="off"
          role="combobox"
          aria-expanded={isOpen}
          aria-controls="address-suggestions"
          aria-activedescendant={activeIndex >= 0 ? `address-option-${activeIndex}` : undefined}
          aria-invalid={!!error}
          className={[
            'w-full bg-[var(--color-surface)]',
            'border rounded-[var(--radius-sm)]',
            'text-[var(--color-text-primary)]',
            'placeholder:text-[var(--color-text-tertiary)]',
            'transition-colors duration-[var(--transition-fast)]',
            'focus:outline-none focus:ring-2 focus:ring-offset-0',
            error
              ? 'border-[var(--color-danger)] focus:ring-[var(--color-danger)]/30'
              : 'border-[var(--color-border)] hover:border-[var(--color-border-strong)] focus:border-[var(--color-primary)] focus:ring-[var(--color-primary)]/20',
            isLarge ? 'h-14 pl-12 pr-12 text-[var(--text-lg)]' : 'h-10 pl-10 pr-10 text-[var(--text-base)]',
          ].join(' ')}
        />

        {isLoading && (
          <span
            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]"
            aria-hidden="true"
          >
            <Loader2 size={isLarge ? 20 : 16} className="animate-spin" />
          </span>
        )}
      </div>

      {error && (
        <p className="mt-1.5 text-[var(--text-xs)] text-[var(--color-danger)]" role="alert">
          {error}
        </p>
      )}

      {isOpen && suggestions.length > 0 && (
        <ul
          ref={listRef}
          id="address-suggestions"
          role="listbox"
          className="absolute z-40 w-full mt-1 py-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden"
          style={{ boxShadow: 'var(--shadow-lg)' }}
        >
          {suggestions.map((suggestion, index) => {
            const isActive = index === activeIndex;
            return (
              <li
                key={`${suggestion.formatted}-${index}`}
                id={`address-option-${index}`}
                role="option"
                aria-selected={isActive}
                onMouseEnter={() => setActiveIndex(index)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  selectAddress(suggestion);
                }}
                className={[
                  'flex items-center gap-3 px-3.5 cursor-pointer',
                  'transition-colors duration-[var(--transition-fast)]',
                  isLarge ? 'py-3' : 'py-2.5',
                  isActive
                    ? 'bg-[var(--color-primary-light)]'
                    : 'hover:bg-[var(--color-bg)]',
                ].join(' ')}
              >
                <MapPin
                  size={16}
                  className="shrink-0"
                  style={{ color: isActive ? 'var(--color-primary)' : 'var(--color-text-tertiary)' }}
                  aria-hidden="true"
                />
                <span
                  className="text-[var(--text-sm)] truncate"
                  style={{ color: isActive ? 'var(--color-primary)' : 'var(--color-text-primary)' }}
                >
                  {suggestion.formatted}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
