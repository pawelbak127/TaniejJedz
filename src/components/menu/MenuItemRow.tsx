'use client';

import { useState, useCallback } from 'react';
import type { MenuItem, Platform } from '@/generated/api-types';
import { PLATFORM_ORDER } from '@/lib/platforms';
import { useComparisonStore } from '@/stores/comparison';
import { useToast } from '@/components/ui/Toast';
import PriceCell from './PriceCell';
import ModifierSelector from './ModifierSelector';
import AddToCartButton from './AddToCartButton';
import FeedbackButton from '@/components/feedback/FeedbackButton';

interface MenuItemRowProps {
  item: MenuItem;
  restaurantId: string;
}

export default function MenuItemRow({ item, restaurantId }: MenuItemRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const addItem = useComparisonStore((s) => s.addItem);
  const { addToast } = useToast();

  const availablePlatforms = PLATFORM_ORDER.filter((p) => item.prices[p]);

  const handleAdd = useCallback(
    (quantity: number, selectedModifiers: Partial<Record<Platform, string[]>>) => {
      const basePrices: Partial<Record<Platform, number>> = {};
      for (const p of availablePlatforms) {
        const price = item.prices[p];
        if (price && price.is_available) {
          basePrices[p] = price.price_grosz;
        }
      }

      addItem({
        canonicalItemId: item.id,
        name: item.name,
        quantity,
        selectedModifiers,
        basePrices,
      });

      setIsExpanded(false);
      addToast(`${item.name} × ${quantity} dodano do koszyka`, 'success');
    },
    [item, addItem, addToast, availablePlatforms],
  );

  return (
    <div className="py-3 border-b border-border last:border-b-0">
      {/* Collapsed row */}
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-text-primary truncate">
              {item.name}
            </h4>
            {item.size_label && (
              <span className="text-xs text-text-tertiary shrink-0">{item.size_label}</span>
            )}
          </div>

          {item.description && (
            <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">
              {item.description}
            </p>
          )}

          {/* Prices */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
            {availablePlatforms.map((platform) => {
              const price = item.prices[platform];
              if (!price) return null;
              return (
                <PriceCell
                  key={platform}
                  platform={platform}
                  price={price}
                  isCheapest={platform === item.cheapest_open_platform}
                />
              );
            })}
          </div>

          {/* Feedback link */}
          <div className="mt-1">
            <FeedbackButton restaurantId={restaurantId} itemId={item.id} />
          </div>
        </div>

        <AddToCartButton
          onClick={() => setIsExpanded(!isExpanded)}
          isExpanded={isExpanded}
        />
      </div>

      {/* Expanded modifier selector */}
      {isExpanded && (
        <div className="mt-3">
          <ModifierSelector
            itemName={item.name}
            platformModifiers={item.platform_modifiers}
            onAdd={handleAdd}
            onCancel={() => setIsExpanded(false)}
          />
        </div>
      )}
    </div>
  );
}
