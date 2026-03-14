'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
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

interface RestaurantListClientProps {
  city: string;
  initialRestaurants: RestaurantSummary[];
  initialTotal: number;
  fetchError: boolean;
}

export default function RestaurantListClient({
  city,
  initialRestaurants,
  initialTotal,
  fetchError,
}: RestaurantListClientProps) {
  const cityDisplay = SUPPORTED_CITIES_DISPLAY[city] || city;
  const { address } = useAddress();

  // Data state — seeded from server
  const [restaurants, setRestaurants] = useState<RestaurantSummary[]>(initialRestaurants);
  const [total, setTotal] = useState(initialTotal);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(
    fetchError ? 'Nie udało się załadować restauracji. Spróbuj ponownie.' : null,
  );

  // Filter state
  const [activeCuisines, setActiveCuisines] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<'relevance' | 'cheapest_delivery' | 'rating'>(
    SEARCH_DEFAULTS.sort_by,
  );
  const [showClosed, setShowClosed] = useState(SEARCH_DEFAULTS.show_closed);

  // Track whether filters changed from defaults (skip refetch on mount)
  const [filtersChanged, setFiltersChanged] = useState(false);

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

  // Refetch only when filters change (not on initial mount — we have SSR data)
  useEffect(() => {
    if (filtersChanged) {
      fetchRestaurants(1, false);
    }
  }, [filtersChanged, fetchRestaurants]);

  const handleCuisineToggle = (cuisine: string) => {
    setFiltersChanged(true);
    setActiveCuisines((prev) =>
      prev.includes(cuisine) ? prev.filter((c) => c !== cuisine) : [...prev, cuisine],
    );
  };

  const handleSortChange = (sort: 'relevance' | 'cheapest_delivery' | 'rating') => {
    setFiltersChanged(true);
    setSortBy(sort);
  };

  const handleShowClosedChange = (show: boolean) => {
    setFiltersChanged(true);
    setShowClosed(show);
  };

  const handleLoadMore = () => {
    fetchRestaurants(page + 1, true);
  };

  const handleRetry = () => {
    setFiltersChanged(true);
    fetchRestaurants(1, false);
  };

  const hasMore = restaurants.length < total;

  return (
    <div className="min-h-screen flex flex-col bg-bg">
      <Header showAddress />

      <main className="flex-1">
        <div className="mx-auto max-w-[1280px] px-4 sm:px-6 py-6">
          {/* Title row */}
          <div className="flex items-baseline justify-between mb-4">
            <h1 className="text-xl font-semibold text-text-primary">
              Restauracje w {cityDisplay}
            </h1>
            {!isLoading && !error && (
              <span className="text-sm text-text-tertiary tabular-nums">
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
              onSortChange={handleSortChange}
              showClosed={showClosed}
              onShowClosedChange={handleShowClosedChange}
            />
          </div>

          {/* Error state */}
          {error && (
            <div className="mb-6 flex items-center gap-3 p-4 rounded-md border border-danger/20 bg-danger/5">
              <AlertCircle size={18} className="shrink-0 text-danger" aria-hidden="true" />
              <p className="flex-1 text-sm text-text-primary">
                {error}
              </p>
              <Button
                variant="outline"
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={handleRetry}
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
                setFiltersChanged(true);
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
                      animationDelay: page === 1 && !filtersChanged ? `${index * 50}ms` : '0ms',
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
