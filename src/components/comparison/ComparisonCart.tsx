'use client';

import { useCallback } from 'react';
import { ShoppingCart, Trash2 } from 'lucide-react';
import { useComparisonStore } from '@/stores/comparison';
import { useComparisonSSE } from '@/hooks/useComparisonSSE';
import { useAddress } from '@/hooks/useAddress';
import { apiClient } from '@/lib/api-client';
import { useToast } from '@/components/ui/Toast';
import Button from '@/components/ui/Button';
import { pluralizeItems, formatPrice } from '@/lib/format';
import { PLATFORM_ORDER, getPlatformMeta } from '@/lib/platforms';
import type { Platform } from '@/generated/api-types';
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

  // SSE connection
  useComparisonSSE(comparisonId);

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

  // Sort platform results: cheapest first
  const sortedResults = Array.from(platformResults.values())
    .filter((r) => r.is_open)
    .sort((a, b) => a.grand_total_grosz - b.grand_total_grosz);

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
          className="text-xs text-text-tertiary hover:text-danger transition-colors duration-fast flex items-center gap-1"
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
                <span className="tabular-nums text-text-primary font-medium">
                  {formatPrice(sub)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Compare button */}
      {!comparisonId && (
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onClick={handleCompare}
          disabled={count === 0}
        >
          Porównaj ceny
        </Button>
      )}

      {/* SSE Status Bar */}
      {comparisonId && <PlatformStatusBar />}

      {/* Savings Banner */}
      <SavingsBanner />

      {/* Platform total cards */}
      {comparisonReady && sortedResults.length > 0 && (
        <div className="flex flex-col gap-3">
          {sortedResults.map((result, index) => (
            <PlatformTotalCard
              key={result.platform}
              result={result}
              isCheapest={result.platform === cheapestPlatform}
              rank={index + 1}
            />
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
      {comparisonReady && (
        <Button
          variant="ghost"
          size="sm"
          onClick={resetComparison}
          fullWidth
        >
          Porównaj ponownie
        </Button>
      )}
    </div>
  );
}
