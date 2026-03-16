'use client';

import { useQuery } from '@tanstack/react-query';
import { AlertCircle, RefreshCw, Clock } from 'lucide-react';
import Header from '@/components/shared/Header';
import Footer from '@/components/shared/Footer';
import { Button } from '@/components/ui';
import { EmptyState } from '@/components/shared';
import PlatformBadges from '@/components/restaurant/PlatformBadges';
import MenuView from '@/components/menu/MenuView';
import MenuSkeleton from '@/components/menu/MenuSkeleton';
import FeedbackButton from '@/components/feedback/FeedbackButton';
import { ComparisonCartWrapper } from '@/components/comparison';
import { apiClient } from '@/lib/api-client';
import type { MenuResponse, Platform, PlatformAvailability } from '@/generated/api-types';

interface RestaurantDetailClientProps {
  city: string;
  restaurantId: string;
  initialMenu: MenuResponse | null;
}

export default function RestaurantDetailClient({
  city,
  restaurantId,
  initialMenu,
}: RestaurantDetailClientProps) {
  const {
    data: menu,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['menu', restaurantId],
    queryFn: () => apiClient.getMenu(restaurantId),
    initialData: initialMenu ?? undefined,
    enabled: !initialMenu, // fetch only if SSR failed
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const showError = (isError || (!menu && !isLoading));
  const errorMessage = error instanceof Error
    ? error.message
    : 'Nie udało się załadować menu. Spróbuj ponownie.';

  const platformsRecord: Partial<Record<Platform, PlatformAvailability>> = {};
  if (menu) {
    for (const p of menu.restaurant.platforms_available) {
      const isOpen = menu.restaurant.platforms_open.includes(p);
      const closedInfo = menu.restaurant.platforms_closed.find((c) => c.platform === p);
      platformsRecord[p] = {
        available: true,
        is_open: isOpen,
        next_open: closedInfo?.next_open,
      };
    }
  }

  const hasClosedPlatforms = menu ? menu.restaurant.platforms_closed.length > 0 : false;

  return (
    <div className="min-h-screen flex flex-col bg-bg">
      <Header showAddress />

      <main className="flex-1">
        <div className="mx-auto max-w-[1280px] px-4 sm:px-6 py-6">
          {/* Restaurant header — visible even during error if we have data */}
          {menu && (
            <div className="mb-6">
              <h1 className="text-2xl font-semibold text-text-primary">
                {menu.restaurant.name}
              </h1>

              <div className="mt-2">
                <PlatformBadges
                  platforms={platformsRecord}
                  showRating
                  size="md"
                />
              </div>

              {hasClosedPlatforms && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {menu.restaurant.platforms_closed.map((c) => (
                    <span
                      key={c.platform}
                      className="inline-flex items-center gap-1 text-xs text-text-tertiary"
                    >
                      <Clock size={11} aria-hidden="true" />
                      {c.platform}: otwiera {c.next_open}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-2">
                <FeedbackButton restaurantId={restaurantId} />
              </div>
            </div>
          )}

          {/* Error state */}
          {showError && !isLoading && (
            <div className="mb-6 flex items-center gap-3 p-4 rounded-md border border-danger/20 bg-danger/5">
              <AlertCircle size={18} className="shrink-0 text-danger" aria-hidden="true" />
              <p className="flex-1 text-sm text-text-primary">{errorMessage}</p>
              <Button
                variant="outline"
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={() => refetch()}
              >
                Ponów
              </Button>
            </div>
          )}

          {/* Loading */}
          {isLoading && <MenuSkeleton />}

          {/* Menu + Cart */}
          {!isLoading && !showError && menu && (
            <div className="lg:flex lg:gap-6">
              <div className="lg:w-[60%] lg:shrink-0">
                <MenuView
                  categories={menu.categories}
                  restaurantId={restaurantId}
                />
              </div>

              <ComparisonCartWrapper restaurantId={restaurantId} />
            </div>
          )}

          {/* Empty menu */}
          {!isLoading && !showError && menu && menu.categories.length === 0 && (
            <EmptyState
              title="Menu jest puste"
              description="Nie znaleźliśmy pozycji w menu tej restauracji."
            />
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
}
