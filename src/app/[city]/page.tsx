'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams } from 'next/navigation';
import { AlertCircle, RefreshCw } from 'lucide-react';
import Header from '@/components/shared/Header';
import Footer from '@/components/shared/Footer';
import RestaurantCard from '@/components/restaurant/RestaurantCard';
import RestaurantFilters from '@/components/restaurant/RestaurantFilters';
import RestaurantListSkeleton from '@/components/restaurant/RestaurantListSkeleton';
import { EmptyState } from '@/components/shared';
import { Button } from '@/components/ui';
import { apiClient, ApiClientError } from '@/lib/api-client';
import { useAddress } from '@/hooks/useAddress';
import { pluralizeRestaurants } from '@/lib/format';
import { SUPPORTED_CITIES_DISPLAY, SEARCH_DEFAULTS } from '@/lib/constants';
import type { RestaurantSummary } from '@/generated/api-types';

export default function CityPage() {
  const params = useParams<{ city: string }>();
  const city = params.city;
  const cityDisplay = SUPPORTED_CITIES_DISPLAY[city] || city;
  const { address } = useAddress();

  // Data state
  const [restaurants, setRestaurants] = useState<RestaurantSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [activeCuisines, setActiveCuisines] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<'relevance' | 'cheapest_delivery' | 'rating'>(
    SEARCH_DEFAULTS.sort_by,
  );
  const [showClosed, setShowClosed] = useState(SEARCH_DEFAULTS.show_closed);

  // Extract unique cuisines from results
  const allCuisines = useMemo(() => {
    const set = new Set<string>();
    restaurants.forEach((r) => r.cuisine_tags.forEach((t) => set.add(t)));
    return Array.from(set).sort();
  }, [restaurants]);

  const fetchRestaurants = useCallback(
    async (pageNum: number, append: boolean) => {
      if (append) {
        setIsLoadingMore(true);
      } else {
        setIsLoading(true);
        setError(null);
      }

      try {
        const response = await apiClient.search({
          address: address?.formatted || cityDisplay,
          latitude: address?.latitude || 52.2297,
          longitude: address?.longitude || 21.0122,
          cuisine_filter: activeCuisines.length > 0 ? activeCuisines : undefined,
          sort_by: sortBy,
          show_closed: showClosed,
          page: pageNum,
          per_page: SEARCH_DEFAULTS.per_page,
        });

        if (append) {
          setRestaurants((prev) => [...prev, ...response.restaurants]);
        } else {
          setRestaurants(response.restaurants);
        }
        setTotal(response.total);
        setPage(pageNum);
      } catch (err) {
        if (err instanceof ApiClientError) {
          setError(err.message);
        } else {
          setError('Nie udało się załadować restauracji. Spróbuj ponownie.');
        }
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [address, activeCuisines, sortBy, showClosed, cityDisplay],
  );

  // Initial fetch + refetch on filter changes
  useEffect(() => {
    fetchRestaurants(1, false);
  }, [fetchRestaurants]);

  const handleCuisineToggle = (cuisine: string) => {
    setActiveCuisines((prev) =>
      prev.includes(cuisine) ? prev.filter((c) => c !== cuisine) : [...prev, cuisine],
    );
  };

  const handleLoadMore = () => {
    fetchRestaurants(page + 1, true);
  };

  const hasMore = restaurants.length < total;

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-bg)]">
      <Header showAddress />

      <main className="flex-1">
        <div className="mx-auto max-w-[1280px] px-4 sm:px-6 py-6">
          {/* Title row */}
          <div className="flex items-baseline justify-between mb-4">
            <h1 className="text-[var(--text-xl)] font-semibold text-[var(--color-text-primary)]">
              Restauracje w {cityDisplay}
            </h1>
            {!isLoading && !error && (
              <span className="text-[var(--text-sm)] text-[var(--color-text-tertiary)] tabular-nums">
                {pluralizeRestaurants(total)}
              </span>
            )}
          </div>

          {/* Filters */}
          <div className="mb-6">
            <RestaurantFilters
              cuisines={allCuisines}
              activeCuisines={activeCuisines}
              onCuisineToggle={handleCuisineToggle}
              sortBy={sortBy}
              onSortChange={setSortBy}
              showClosed={showClosed}
              onShowClosedChange={setShowClosed}
            />
          </div>

          {/* Error state */}
          {error && (
            <div className="mb-6 flex items-center gap-3 p-4 rounded-[var(--radius-md)] border border-[var(--color-danger)]/20 bg-[var(--color-danger)]/5">
              <AlertCircle size={18} className="shrink-0 text-[var(--color-danger)]" aria-hidden="true" />
              <p className="flex-1 text-[var(--text-sm)] text-[var(--color-text-primary)]">
                {error}
              </p>
              <Button
                variant="outline"
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={() => fetchRestaurants(1, false)}
              >
                Ponów
              </Button>
            </div>
          )}

          {/* Loading skeleton */}
          {isLoading && <RestaurantListSkeleton />}

          {/* Empty state */}
          {!isLoading && !error && restaurants.length === 0 && (
            <EmptyState
              title="Nie znaleźliśmy restauracji w tej okolicy"
              description="Spróbuj inny adres lub zmień filtry."
              actionLabel="Wyczyść filtry"
              onAction={() => {
                setActiveCuisines([]);
                setSortBy('relevance');
                setShowClosed(false);
              }}
            />
          )}

          {/* Restaurant list */}
          {!isLoading && restaurants.length > 0 && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {restaurants.map((restaurant, index) => (
                  <div
                    key={restaurant.id}
                    className="animate-fade-in-item"
                    style={{
                      animationDelay: page === 1 ? `${index * 50}ms` : '0ms',
                    }}
                  >
                    <RestaurantCard restaurant={restaurant} city={city} />
                  </div>
                ))}
              </div>

              {/* Load more */}
              {hasMore && (
                <div className="mt-6 flex justify-center">
                  <Button
                    variant="outline"
                    size="md"
                    loading={isLoadingMore}
                    onClick={handleLoadMore}
                  >
                    Załaduj więcej
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </main>

      <Footer />

      <style jsx>{`
        @keyframes fade-in-item {
          from {
            opacity: 0;
            transform: translateY(6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @media (prefers-reduced-motion: no-preference) {
          .animate-fade-in-item {
            animation: fade-in-item 300ms ease-out both;
          }
        }
      `}</style>
    </div>
  );
}
