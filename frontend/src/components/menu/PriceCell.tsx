import type { Platform, PlatformPrice } from '@/generated/api-types';
import { getPlatformMeta } from '@/lib/platforms';
import PriceDisplay from '@/components/shared/PriceDisplay';
import StalenessIndicator from '@/components/shared/StalenessIndicator';

interface PriceCellProps {
  platform: Platform;
  price: PlatformPrice;
  isCheapest: boolean;
}

export default function PriceCell({ platform, price, isCheapest }: PriceCellProps) {
  const meta = getPlatformMeta(platform);

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1.5">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ backgroundColor: meta.color }}
          aria-hidden="true"
        />
        <span className="text-xs font-medium text-text-secondary">
          {meta.shortName}:
        </span>
        <PriceDisplay
          priceGrosz={price.price_grosz}
          isCheapest={isCheapest}
          isUnavailable={!price.is_available}
          isClosed={!price.is_open}
          className="text-sm"
        />
      </div>
      <StalenessIndicator lastChecked={price.last_checked} className="ml-3.5" />
    </div>
  );
}
