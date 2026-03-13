'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Clock } from 'lucide-react';
import type { RestaurantSummary } from '@/generated/api-types';
import { formatPrice } from '@/lib/format';
import { getPlatformName } from '@/lib/platforms';
import PlatformBadges from './PlatformBadges';

interface RestaurantCardProps {
  restaurant: RestaurantSummary;
  city: string;
}

export default function RestaurantCard({ restaurant, city }: RestaurantCardProps) {
  const [imgError, setImgError] = useState(false);
  const isClosed = restaurant.cheapest_open_platform === null;
  const slug = restaurant.id;
  const initial = restaurant.name.charAt(0).toUpperCase();

  const openPlatformCount = Object.values(restaurant.platforms).filter(
    (p) => p.available && p.is_open,
  ).length;

  const closedPlatform = Object.entries(restaurant.platforms).find(
    ([, v]) => v.available && !v.is_open && v.next_open,
  );
  const nextOpenTime = closedPlatform ? closedPlatform[1].next_open : undefined;

  const showImage = restaurant.image_url && !imgError;

  return (
    <Link
      href={`/${city}/${slug}`}
      className={[
        'group flex gap-3 p-4',
        'bg-surface border border-border',
        'rounded-md',
        'transition-all duration-fast',
        'hover:border-border-strong hover:shadow-sm',
        isClosed ? 'opacity-60' : '',
      ].join(' ')}
      prefetch={false}
    >
      {/* Image / placeholder */}
      <div
        className="shrink-0 w-[80px] h-[80px] lg:w-[100px] lg:h-[80px] rounded-sm overflow-hidden flex items-center justify-center bg-border"
        aria-hidden="true"
      >
        {showImage ? (
          <Image
            src={restaurant.image_url!}
            alt={`${restaurant.name} — zdjęcie restauracji`}
            width={100}
            height={80}
            className="w-full h-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <span className="text-lg font-semibold text-text-tertiary">
            {initial}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 flex flex-col gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-text-primary truncate group-hover:text-primary transition-colors duration-fast">
              {restaurant.name}
            </h3>
            <p className="text-sm text-text-secondary truncate">
              {restaurant.address}
              <span className="mx-1.5">&middot;</span>
              {restaurant.cuisine_tags.join(', ')}
            </p>
          </div>

          {isClosed && (
            <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-border text-xs font-medium text-text-secondary uppercase tracking-[0.03em]">
              <Clock size={11} aria-hidden="true" />
              Zamknięte
            </span>
          )}
        </div>

        <PlatformBadges platforms={restaurant.platforms} />

        {!isClosed && openPlatformCount >= 2 && restaurant.cheapest_delivery_fee_grosz !== null && restaurant.cheapest_open_platform && (
          <p className="text-sm text-text-secondary">
            Najtańsza dostawa:{' '}
            <span className="font-medium text-text-primary tabular-nums">
              {formatPrice(restaurant.cheapest_delivery_fee_grosz)}
            </span>
            {' '}
            <span className="text-text-tertiary">
              ({getPlatformName(restaurant.cheapest_open_platform)})
            </span>
          </p>
        )}

        {isClosed && nextOpenTime && (
          <p className="text-sm text-text-tertiary">
            Otwiera: {nextOpenTime}
          </p>
        )}
      </div>
    </Link>
  );
}
