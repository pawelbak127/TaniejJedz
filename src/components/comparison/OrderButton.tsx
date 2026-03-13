'use client';

import { ExternalLink } from 'lucide-react';
import type { PlatformComparisonResult } from '@/generated/api-types';
import { getPlatformMeta } from '@/lib/platforms';
import { formatPrice } from '@/lib/format';
import { useClipboardCopy } from '@/hooks/useClipboardCopy';

interface OrderButtonProps {
  result: PlatformComparisonResult;
  isCheapest: boolean;
}

function buildClipboardText(result: PlatformComparisonResult): string {
  const meta = getPlatformMeta(result.platform);
  const lines = [
    `Zamówienie na ${meta.name}`,
    '---',
    ...result.items.map(
      (item) => `${item.name} × ${item.quantity} — ${formatPrice(item.item_total_grosz)}`,
    ),
    '---',
    `Produkty: ${formatPrice(result.items_total_grosz)}`,
    `Dostawa: ${formatPrice(result.delivery_fee_grosz)}`,
  ];

  if (result.promotion_discount_grosz > 0) {
    lines.push(`Promocja: -${formatPrice(result.promotion_discount_grosz)}`);
  }

  lines.push(`Razem: ${formatPrice(result.grand_total_grosz)}`);
  lines.push('', 'Porównano na TaniejJedz.pl');

  return lines.join('\n');
}

export default function OrderButton({ result, isCheapest }: OrderButtonProps) {
  const { copy } = useClipboardCopy();
  const meta = getPlatformMeta(result.platform);

  const handleClick = async () => {
    const text = buildClipboardText(result);
    await copy(text, 'Podsumowanie zamówienia skopiowane do schowka.');
    window.open(result.deep_link, '_blank');
    console.log('[ANALYTICS] redirect_clicked', result.platform, result.grand_total_grosz);
  };

  if (isCheapest) {
    return (
      <button
        onClick={handleClick}
        className="w-full min-h-[44px] h-11 px-4 rounded-sm font-medium text-sm text-text-inverse flex items-center justify-center gap-2 transition-colors duration-fast hover:opacity-90 active:opacity-80"
        style={{ backgroundColor: 'var(--color-accent-dark)' }}
      >
        <span className="truncate">Zamów na {meta.name} — {formatPrice(result.grand_total_grosz)}</span>
        <ExternalLink size={14} className="shrink-0" aria-hidden="true" />
      </button>
    );
  }

  return (
    <button
      onClick={handleClick}
      className="w-full min-h-[44px] h-10 px-4 rounded-sm font-medium text-sm text-text-primary border border-border-strong flex items-center justify-center gap-2 transition-colors duration-fast hover:bg-bg hover:border-text-tertiary active:bg-border"
    >
      <span className="truncate">Zamów na {meta.name} — {formatPrice(result.grand_total_grosz)}</span>
      <ExternalLink size={14} className="shrink-0 text-text-tertiary" aria-hidden="true" />
    </button>
  );
}
