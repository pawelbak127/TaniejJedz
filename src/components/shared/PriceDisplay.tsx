import { formatPrice } from '@/lib/format';

interface PriceDisplayProps {
  priceGrosz: number;
  isCheapest?: boolean;
  isUnavailable?: boolean;
  isClosed?: boolean;
  className?: string;
}

export default function PriceDisplay({
  priceGrosz,
  isCheapest = false,
  isUnavailable = false,
  isClosed = false,
  className = '',
}: PriceDisplayProps) {
  if (isUnavailable) {
    return (
      <span className={`tabular-nums text-text-tertiary line-through ${className}`}>
        {formatPrice(priceGrosz)}
      </span>
    );
  }

  if (isClosed) {
    return (
      <span className={`tabular-nums text-text-tertiary ${className}`}>
        {formatPrice(priceGrosz)}{' '}
        <span className="text-xs">(zamkn.)</span>
      </span>
    );
  }

  return (
    <span
      className={[
        'tabular-nums font-medium',
        isCheapest ? 'text-accent-dark' : 'text-text-primary',
        className,
      ].join(' ')}
    >
      {formatPrice(priceGrosz)}
      {isCheapest && <span className="ml-0.5 text-xs">★</span>}
    </span>
  );
}
