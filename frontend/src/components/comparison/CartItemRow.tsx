'use client';

import { Minus, Plus, Trash2 } from 'lucide-react';
import { useComparisonStore, type CartItemState } from '@/stores/comparison';
import { formatPrice } from '@/lib/format';
import { PLATFORM_ORDER, getPlatformMeta } from '@/lib/platforms';

interface CartItemRowProps {
  item: CartItemState;
}

export default function CartItemRow({ item }: CartItemRowProps) {
  const updateQuantity = useComparisonStore((s) => s.updateQuantity);
  const removeItem = useComparisonStore((s) => s.removeItem);

  const platforms = PLATFORM_ORDER.filter((p) => item.basePrices[p] !== undefined);
  const hasNoPlatforms = platforms.length === 0;

  return (
    <div className={`py-3 border-b border-border last:border-b-0 ${hasNoPlatforms ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={`text-sm font-medium truncate ${hasNoPlatforms ? 'line-through text-text-tertiary' : 'text-text-primary'}`}>
            {item.name}
          </p>

          {hasNoPlatforms && (
            <p className="text-xs text-danger mt-0.5">
              Niedostępne na żadnej platformie
            </p>
          )}

          {/* Modifier summary per platform */}
          {platforms.map((p) => {
            const mods = item.selectedModifiers[p];
            if (!mods || mods.length === 0) return null;
            return (
              <p key={p} className="text-xs text-text-tertiary mt-0.5 truncate">
                + {mods.length} {mods.length === 1 ? 'modyfikator' : 'modyfikatory'} ({getPlatformMeta(p).shortName})
              </p>
            );
          })}
        </div>

        <button
          onClick={() => removeItem(item.canonicalItemId)}
          className="shrink-0 p-1.5 min-w-[44px] min-h-[44px] flex items-center justify-center text-text-tertiary hover:text-danger transition-colors duration-fast"
          aria-label={`Usuń ${item.name}`}
        >
          <Trash2 size={14} />
        </button>
      </div>

      {/* Quantity controls */}
      {!hasNoPlatforms && (
        <div className="flex items-center gap-2 mt-2">
          <div className="flex items-center gap-0">
            <button
              onClick={() => updateQuantity(item.canonicalItemId, item.quantity - 1)}
              className="w-8 h-8 flex items-center justify-center rounded-l-sm border border-border text-text-secondary hover:bg-bg transition-colors duration-fast"
              aria-label="Zmniejsz ilość"
            >
              <Minus size={12} />
            </button>
            <span className="w-9 h-8 flex items-center justify-center border-y border-border text-xs font-medium text-text-primary tabular-nums">
              {item.quantity}
            </span>
            <button
              onClick={() => updateQuantity(item.canonicalItemId, item.quantity + 1)}
              className="w-8 h-8 flex items-center justify-center rounded-r-sm border border-border text-text-secondary hover:bg-bg transition-colors duration-fast"
              aria-label="Zwiększ ilość"
            >
              <Plus size={12} />
            </button>
          </div>

          {/* Per-platform subtotals */}
          <div className="flex-1 flex flex-wrap gap-x-3 gap-y-0.5 justify-end">
            {platforms.map((p) => {
              const base = item.basePrices[p];
              if (base === undefined) return null;
              const subtotal = base * item.quantity;
              const meta = getPlatformMeta(p);
              return (
                <span key={p} className="text-xs text-text-secondary tabular-nums">
                  <span
                    className="inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle"
                    style={{ backgroundColor: meta.color }}
                    aria-hidden="true"
                  />
                  {formatPrice(subtotal)}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
