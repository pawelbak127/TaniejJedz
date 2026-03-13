'use client';

import { useState, useEffect } from 'react';
import { Star } from 'lucide-react';
import type { PlatformComparisonResult } from '@/generated/api-types';
import { getPlatformMeta } from '@/lib/platforms';
import { formatPrice } from '@/lib/format';
import AnimatedPrice from '@/components/shared/AnimatedPrice';

interface PlatformTotalCardProps {
  result: PlatformComparisonResult;
  isCheapest: boolean;
  rank: number;
}

export default function PlatformTotalCard({
  result,
  isCheapest,
}: PlatformTotalCardProps) {
  const meta = getPlatformMeta(result.platform);
  const [justAppeared, setJustAppeared] = useState(true);

  // Brief highlight when card first mounts
  useEffect(() => {
    const timer = setTimeout(() => setJustAppeared(false), 600);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div
      className={[
        'rounded-md border p-3 transition-shadow duration-slow',
        isCheapest
          ? 'border-savings-border bg-savings-bg'
          : 'border-border bg-surface',
        justAppeared ? 'shadow-md' : '',
      ].join(' ')}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: meta.color }}
            aria-hidden="true"
          />
          <span className="text-sm font-semibold text-text-primary">
            {meta.name}
          </span>
          {isCheapest && (
            <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-savings-text bg-savings-bg border border-savings-border rounded-full px-2 py-0.5">
              <Star size={10} aria-hidden="true" />
              NAJTAŃSZY
            </span>
          )}
        </div>
        {result.estimated_delivery_minutes !== null && (
          <span className="text-xs text-text-tertiary">
            ~{result.estimated_delivery_minutes} min
          </span>
        )}
      </div>

      {/* Line items */}
      <div className="flex flex-col gap-1 text-xs">
        <div className="flex justify-between text-text-secondary">
          <span>Produkty</span>
          <span className="tabular-nums">{formatPrice(result.items_total_grosz)}</span>
        </div>

        <div className="flex justify-between text-text-secondary">
          <span>Dostawa</span>
          <span className="tabular-nums">{formatPrice(result.delivery_fee_grosz)}</span>
        </div>

        {result.promotion_discount_grosz > 0 && (
          <div className="flex justify-between text-accent-dark font-medium">
            <span>Promocja</span>
            <span className="tabular-nums">
              -{formatPrice(result.promotion_discount_grosz)}
            </span>
          </div>
        )}

        <div className="flex justify-between pt-1.5 mt-0.5 border-t border-border text-sm font-semibold text-text-primary">
          <span>Razem</span>
          <AnimatedPrice
            valueGrosz={result.grand_total_grosz}
            className="font-semibold"
          />
        </div>
      </div>

      {/* Missing items */}
      {result.missing_items.length > 0 && (
        <p className="mt-2 text-xs text-warning">
          {result.missing_items.length} {result.missing_items.length === 1 ? 'produkt niedostępny' : 'produkty niedostępne'}
        </p>
      )}

      {/* Minimum order */}
      {!result.meets_minimum_order && result.minimum_order_grosz && (
        <p className="mt-1 text-xs text-danger">
          Min. zamówienie: {formatPrice(result.minimum_order_grosz)}
        </p>
      )}
    </div>
  );
}
