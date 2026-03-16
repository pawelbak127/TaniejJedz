'use client';

import { useState } from 'react';
import { useComparisonStore } from '@/stores/comparison';
import { pluralizeItems, formatPrice } from '@/lib/format';
import { PLATFORM_ORDER } from '@/lib/platforms';
import { ShoppingCart } from 'lucide-react';
import ComparisonCart from './ComparisonCart';
import BottomSheet from './BottomSheet';

interface ComparisonCartWrapperProps {
  restaurantId: string;
}

export default function ComparisonCartWrapper({ restaurantId }: ComparisonCartWrapperProps) {
  return (
    <>
      {/* Desktop: sidebar */}
      <div className="hidden lg:block lg:w-[40%]">
        <div className="sticky top-4 border border-border rounded-md bg-surface p-4 max-h-[calc(100vh-2rem)] overflow-y-auto">
          <ComparisonCart restaurantId={restaurantId} />
        </div>
      </div>

      {/* Mobile: bottom sheet */}
      <div className="lg:hidden">
        <MobileCart restaurantId={restaurantId} />
      </div>
    </>
  );
}

function MobileCart({ restaurantId }: { restaurantId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const itemCount = useComparisonStore((s) => s.itemCount);
  const estimatedSubtotal = useComparisonStore((s) => s.estimatedSubtotal);
  const comparisonReady = useComparisonStore((s) => s.comparisonReady);
  const cheapestPlatform = useComparisonStore((s) => s.cheapestPlatform);
  const platformResults = useComparisonStore((s) => s.platformResults);

  const count = itemCount();

  if (count === 0) return null;

  // Find cheapest estimated subtotal for peek display
  let cheapestEstimate = Infinity;
  for (const p of PLATFORM_ORDER) {
    const sub = estimatedSubtotal(p);
    if (sub > 0 && sub < cheapestEstimate) {
      cheapestEstimate = sub;
    }
  }

  let peekTotal = cheapestEstimate < Infinity ? formatPrice(cheapestEstimate) : '—';
  if (comparisonReady && cheapestPlatform) {
    const result = platformResults.get(cheapestPlatform);
    if (result) {
      peekTotal = formatPrice(result.grand_total_grosz);
    }
  }

  const peekContent = (
    <div className="w-full flex items-center justify-between">
      <div className="flex items-center gap-2">
        <ShoppingCart size={16} className="text-primary" aria-hidden="true" />
        <span className="text-sm font-medium text-text-primary">
          Koszyk ({pluralizeItems(count)})
        </span>
      </div>
      <span className="text-sm font-semibold text-text-primary tabular-nums">
        od {peekTotal}
      </span>
    </div>
  );

  return (
    <BottomSheet
      peekContent={peekContent}
      open={isOpen}
      onOpenChange={setIsOpen}
    >
      <ComparisonCart restaurantId={restaurantId} />
    </BottomSheet>
  );
}
