'use client';

import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, RefreshCw } from 'lucide-react';
import Header from '@/components/shared/Header';
import Footer from '@/components/shared/Footer';
import RestaurantCard from '@/components/restaurant/RestaurantCard';
import RestaurantFilters from '@/components/restaurant/RestaurantFilters';
import RestaurantListSkeleton from '@/components/restaurant/RestaurantListSkeleton';
import { EmptyState } from '@/components/shared';
import { Button } from '@/components/ui';
import { apiClient } from '@/lib/api-client';
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

  // Filter state
  const [activeCuisines, setActiveCuisines] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<'relevance' | 'cheapest_delivery' | 'rating'>(
    SEARCH_DEFAULTS.sort_by,
  );
  const [showClosed, setShowClosed] = useState(SEARCH_DEFAULTS.show_closed);
  const [page, setPage] = useState(1);

  // Track whether we should use SSR data or fetch fresh
  const [filtersChanged, setFiltersChanged] = useState(false);

  const queryKey = ['restaurants', city, activeCuisines, sortBy, showClosed, page, address?.formatted];

  const {
    data,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey,
    queryFn: () =>
      apiClient.search({
        address: address?.formatted || cityDisplay,
        latitude: address?.latitude || 52.2297,
        longitude: address?.longitude || 21.0122,
        cuisine_filter: activeCuisines.length > 0 ? activeCuisines : undefined,
        sort_by: sortBy,
        show_closed: showClosed,
        page,
        per_page: SEARCH_DEFAULTS.per_page,
      }),
    // Use SSR data on first load, fetch on filter change
    enabled: filtersChanged || fetchError,
    initialData: !filtersChanged && !fetchError
      ? {
          restaurants: initialRestaurants,
          total: initialTotal,
          page: 1,
          per_page: SEARCH_DEFAULTS.per_page,
          city,
          data_freshness: {} as Record<string, { checked_at: string; is_live: boolean }>,
        }
      : undefined,
    staleTime: 30_000,
  });

  const restaurants = data?.restaurants ?? [];
  const total = data?.total ?? 0;

  // Accumulate pages for "load more"
  const [extraPages, setExtraPages] = useState<RestaurantSummary[]>([]);

  const allRestaurants = useMemo(() => {
    if (page === 1) return restaurants;
    return [...restaurants, ...extraPages];
  }, [restaurants, extraPages, page]);

  const allCuisines = useMemo(() => {
    const set = new Set<string>();
    allRestaurants.forEach((r) => r.cuisine_tags.forEach((t) => set.add(t)));
    return Array.from(set).sort();
  }, [allRestaurants]);

  const handleCuisineToggle = (cuisine: string) => {
    setFiltersChanged(true);
    setPage(1);
    setExtraPages([]);
    setActiveCuisines((prev) =>
      prev.includes(cuisine) ? prev.filter((c) => c !== cuisine) : [...prev, cuisine],
    );
  };

  const handleSortChange = (sort: 'relevance' | 'cheapest_delivery' | 'rating') => {
    setFiltersChanged(true);
    setPage(1);
    setExtraPages([]);
    setSortBy(sort);
  };

  const handleShowClosedChange = (show: boolean) => {
    setFiltersChanged(true);
    setPage(1);
    setExtraPages([]);
    setShowClosed(show);
  };

  const {
    isFetching: isLoadingMore,
    refetch: refetchMore,
  } = useQuery({
    queryKey: ['restaurants-more', city, activeCuisines, sortBy, showClosed, page],
    queryFn: async () => {
      const res = await apiClient.search({
        address: address?.formatted || cityDisplay,
        latitude: address?.latitude || 52.2297,
        longitude: address?.longitude || 21.0122,
        cuisine_filter: activeCuisines.length > 0 ? activeCuisines : undefined,
        sort_by: sortBy,
        show_closed: showClosed,
        page,
        per_page: SEARCH_DEFAULTS.per_page,
      });
      setExtraPages((prev) => [...prev, ...res.restaurants]);
      return res;
    },
    enabled: false, // manual trigger only
  });

  const handleLoadMore = useCallback(() => {
    setPage((p) => p + 1);
    setTimeout(() => refetchMore(), 0);
  }, [refetchMore]);

  const hasMore = allRestaurants.length < total;
  const showLoading = isLoading && filtersChanged;
  const showError = (isError || fetchError) && !isFetching;
  const errorMessage = error instanceof Error
    ? error.message
    : 'Nie udało się załadować restauracji. Spróbuj ponownie.';

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
            {!showLoading && !showError && (
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
          {showError && (
            <div className="mb-6 flex items-center gap-3 p-4 rounded-md border border-danger/20 bg-danger/5">
              <AlertCircle size={18} className="shrink-0 text-danger" aria-hidden="true" />
              <p className="flex-1 text-sm text-text-primary">{errorMessage}</p>
              <Button
                variant="outline"
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={() => {
                  setFiltersChanged(true);
                  refetch();
                }}
              >
                Ponów
              </Button>
            </div>
          )}

          {/* Loading skeleton */}
          {showLoading && <RestaurantListSkeleton />}

          {/* Empty state */}
          {!showLoading && !showError && allRestaurants.length === 0 && (
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
          {!showLoading && allRestaurants.length > 0 && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {allRestaurants.map((restaurant, index) => (
                  <div
                    key={restaurant.id}
                    className="animate-fade-in-up"
                    style={{
                      animationDelay: !filtersChanged ? `${index * 50}ms` : '0ms',
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
    </div>
  );
}
