'use client';

import { useCallback } from 'react';
import { ShoppingCart, Trash2, AlertCircle, RefreshCw, WifiOff } from 'lucide-react';
import { useComparisonStore } from '@/stores/comparison';
import { useComparisonSSE } from '@/hooks/useComparisonSSE';
import { useAddress } from '@/hooks/useAddress';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ui/Toast';
import Button from '@/components/ui/Button';
import AnimatedPrice from '@/components/shared/AnimatedPrice';
import { pluralizeItems } from '@/lib/format';
import { PLATFORM_ORDER, getPlatformMeta } from '@/lib/platforms';
import CartItemRow from './CartItemRow';
import PlatformStatusBar from './PlatformStatusBar';
import PlatformTotalCard from './PlatformTotalCard';
import SavingsBanner from './SavingsBanner';
import OrderButton from './OrderButton';

interface ComparisonCartProps {
  restaurantId: string;
}

export default function ComparisonCart({ restaurantId }: ComparisonCartProps) {
  const items = useComparisonStore((s) => s.items);
  const clearCart = useComparisonStore((s) => s.clearCart);
  const comparisonId = useComparisonStore((s) => s.comparisonId);
  const setComparisonId = useComparisonStore((s) => s.setComparisonId);
  const comparisonReady = useComparisonStore((s) => s.comparisonReady);
  const cheapestPlatform = useComparisonStore((s) => s.cheapestPlatform);
  const platformResults = useComparisonStore((s) => s.platformResults);
  const resetComparison = useComparisonStore((s) => s.resetComparison);
  const itemCount = useComparisonStore((s) => s.itemCount);
  const estimatedSubtotal = useComparisonStore((s) => s.estimatedSubtotal);

  const { address } = useAddress();
  const { addToast } = useToast();

  const { sseError, retrySSE } = useComparisonSSE(comparisonId);

  const count = itemCount();
  const itemsArray = Array.from(items.values());

  const handleCompare = useCallback(async () => {
    if (count === 0) return;

    const cartItems = itemsArray.map((item) => ({
      canonical_item_id: item.canonicalItemId,
      quantity: item.quantity,
      selected_modifiers: item.selectedModifiers,
    }));

    try {
      const response = await apiClient.startComparison({
        restaurant_id: restaurantId,
        address: {
          latitude: address?.latitude || 52.2297,
          longitude: address?.longitude || 21.0122,
        },
        items: cartItems,
      });

      setComparisonId(response.comparison_id);
    } catch {
      addToast('Nie udało się rozpocząć porównania. Spróbuj ponownie.', 'error');
    }
  }, [count, itemsArray, restaurantId, address, setComparisonId, addToast]);

  const handleFullRetry = useCallback(() => {
    resetComparison();
    // Small delay so store resets before re-triggering
    setTimeout(() => handleCompare(), 50);
  }, [resetComparison, handleCompare]);

  const sortedResults = Array.from(platformResults.values())
    .filter((r) => r.is_open)
    .sort((a, b) => a.grand_total_grosz - b.grand_total_grosz);

  const allFailed = comparisonReady && sortedResults.length === 0 && cheapestPlatform === null;

  // === Empty state ===
  if (count === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
        <ShoppingCart size={32} className="text-text-tertiary mb-3" aria-hidden="true" />
        <p className="text-sm font-medium text-text-secondary">
          Twój koszyk porównania
        </p>
        <p className="text-xs text-text-tertiary mt-1">
          Dodaj produkty z menu, aby porównać ceny między platformami.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">
          Twój koszyk ({pluralizeItems(count)})
        </h3>
        <button
          onClick={clearCart}
          className="text-xs text-text-tertiary hover:text-danger transition-colors duration-fast flex items-center gap-1 touch-target justify-center"
        >
          <Trash2 size={12} />
          Wyczyść
        </button>
      </div>

      {/* Cart items */}
      <div className="border-t border-border">
        {itemsArray.map((item) => (
          <CartItemRow key={item.canonicalItemId} item={item} />
        ))}
      </div>

      {/* Estimated subtotals before comparison */}
      {!comparisonId && (
        <div className="flex flex-col gap-1 p-3 rounded-md bg-bg">
          <p className="text-xs font-medium text-text-secondary mb-1">
            Szacunkowe sumy (bez dostawy):
          </p>
          {PLATFORM_ORDER.map((p) => {
            const sub = estimatedSubtotal(p);
            if (sub === 0) return null;
            const meta = getPlatformMeta(p);
            return (
              <div key={p} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-text-secondary">
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: meta.color }}
                    aria-hidden="true"
                  />
                  {meta.shortName}
                </span>
                <AnimatedPrice
                  valueGrosz={sub}
                  className="text-text-primary font-medium text-xs"
                />
              </div>
            );
          })}
        </div>
      )}

      {/* Compare button */}
      {!comparisonId && (
        <div className="relative group">
          <Button
            variant="primary"
            size="lg"
            fullWidth
            onClick={handleCompare}
            disabled={count === 0}
          >
            Porównaj ceny
          </Button>
          {count === 0 && (
            <span className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-1 rounded-sm bg-text-primary text-text-inverse text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
              Dodaj produkty do koszyka
            </span>
          )}
        </div>
      )}

      {/* SSE Status Bar */}
      {comparisonId && <PlatformStatusBar />}

      {/* SSE connection error — prominent banner with retry options */}
      {sseError && (
        <div className="flex flex-col gap-3 p-4 rounded-md border border-danger/20 bg-danger/5">
          <div className="flex items-center gap-3">
            <WifiOff size={20} className="shrink-0 text-danger" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                Połączenie przerwane
              </p>
              <p className="text-xs text-text-secondary mt-0.5">
                Nie udało się pobrać wyników od niektórych platform. Sprawdź połączenie z internetem.
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" icon={<RefreshCw size={12} />} onClick={retrySSE}>
              Wznów połączenie
            </Button>
            <Button variant="ghost" size="sm" onClick={handleFullRetry}>
              Porównaj od nowa
            </Button>
          </div>
        </div>
      )}

      {/* All platforms failed */}
      {allFailed && !sseError && (
        <div className="flex flex-col items-center gap-3 p-4 rounded-md border border-danger/20 bg-danger/5 text-center">
          <AlertCircle size={24} className="text-danger" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">
            Nie udało się pobrać cen
          </p>
          <p className="text-xs text-text-secondary">
            Żadna platforma nie odpowiedziała. Spróbuj za chwilę.
          </p>
          <Button
            variant="outline"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={handleFullRetry}
          >
            Spróbuj ponownie
          </Button>
        </div>
      )}

      {/* Savings Banner */}
      <SavingsBanner />

      {/* Platform total cards */}
      {comparisonReady && sortedResults.length > 0 && (
        <div className="flex flex-col gap-3">
          {sortedResults.map((result, index) => (
            <div
              key={result.platform}
              className="animate-fade-in-up"
              style={{ animationDelay: `${index * 80}ms` }}
            >
              <PlatformTotalCard
                result={result}
                isCheapest={result.platform === cheapestPlatform}
                rank={index + 1}
              />
            </div>
          ))}
        </div>
      )}

      {/* Order buttons */}
      {comparisonReady && sortedResults.length > 0 && (
        <div className="flex flex-col gap-2">
          {sortedResults.map((result) => (
            <OrderButton
              key={result.platform}
              result={result}
              isCheapest={result.platform === cheapestPlatform}
            />
          ))}
        </div>
      )}

      {/* Compare again */}
      {comparisonReady && !sseError && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => resetComparison()}
          fullWidth
        >
          Porównaj ponownie
        </Button>
      )}
    </div>
  );
}
