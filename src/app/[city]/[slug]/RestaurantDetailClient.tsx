'use client';

import { useState, useCallback } from 'react';
import { AlertCircle, RefreshCw, Clock } from 'lucide-react';
import Header from '@/components/shared/Header';
import Footer from '@/components/shared/Footer';
import { Button } from '@/components/ui';
import { EmptyState } from '@/components/shared';
import PlatformBadges from '@/components/restaurant/PlatformBadges';
import MenuView from '@/components/menu/MenuView';
import MenuSkeleton from '@/components/menu/MenuSkeleton';
import FeedbackButton from '@/components/feedback/FeedbackButton';
import { apiClient, ApiClientError } from '@/lib/api-client';
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
  const [menu, setMenu] = useState<MenuResponse | null>(initialMenu);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialMenu === null ? 'Nie udało się załadować menu. Spróbuj ponownie.' : null);

  const fetchMenu = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getMenu(restaurantId);
      setMenu(data);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('Nie udało się załadować menu. Spróbuj ponownie.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [restaurantId]);

  // Build platforms record for PlatformBadges from menu data
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
          {/* Restaurant header — always visible even on error */}
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
          {error && !isLoading && (
            <div className="mb-6 flex items-center gap-3 p-4 rounded-md border border-danger/20 bg-danger/5">
              <AlertCircle size={18} className="shrink-0 text-danger" aria-hidden="true" />
              <p className="flex-1 text-sm text-text-primary">{error}</p>
              <Button
                variant="outline"
                size="sm"
                icon={<RefreshCw size={14} />}
                onClick={fetchMenu}
              >
                Ponów
              </Button>
            </div>
          )}

          {/* Loading */}
          {isLoading && <MenuSkeleton />}

          {/* Menu content */}
          {!isLoading && !error && menu && (
            <div className="lg:flex lg:gap-6">
              {/* Menu — 60% on desktop, full width on mobile */}
              <div className="lg:w-[60%] lg:shrink-0">
                <MenuView
                  categories={menu.categories}
                  restaurantId={restaurantId}
                />
              </div>

              {/* Cart placeholder — Etap 7 */}
              <div className="hidden lg:block lg:w-[40%]">
                <div className="sticky top-4 border border-border rounded-md bg-surface p-4">
                  <p className="text-sm font-medium text-text-secondary">
                    Twój koszyk porównania
                  </p>
                  <p className="text-xs text-text-tertiary mt-1">
                    Dodaj produkty z menu, aby porównać ceny między platformami.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Empty menu */}
          {!isLoading && !error && menu && menu.categories.length === 0 && (
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
