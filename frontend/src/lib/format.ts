const priceFormatter = new Intl.NumberFormat('pl-PL', {
  style: 'currency',
  currency: 'PLN',
});

export function formatPrice(grosz: number): string {
  return priceFormatter.format(grosz / 100);
}

export function formatPriceShort(grosz: number): string {
  const value = grosz / 100;
  return `${value.toFixed(2).replace('.', ',')} zł`;
}

const relativeTimeFormatter = new Intl.RelativeTimeFormat('pl-PL', {
  numeric: 'auto',
  style: 'short',
});

export function formatRelativeTime(isoDatetime: string): string {
  const now = Date.now();
  const then = new Date(isoDatetime).getTime();
  const diffSeconds = Math.round((then - now) / 1000);
  const diffMinutes = Math.round(diffSeconds / 60);

  if (Math.abs(diffMinutes) < 1) {
    return 'teraz';
  }
  if (Math.abs(diffMinutes) < 60) {
    return relativeTimeFormatter.format(diffMinutes, 'minute');
  }
  const diffHours = Math.round(diffMinutes / 60);
  return relativeTimeFormatter.format(diffHours, 'hour');
}

export function formatDeliveryTime(minutes: number | null): string {
  if (minutes === null) return '—';
  return `${minutes} min`;
}

export function pluralizeRestaurants(count: number): string {
  if (count === 1) return '1 restauracja';
  if (count >= 2 && count <= 4) return `${count} restauracje`;
  return `${count} restauracji`;
}

export function pluralizeItems(count: number): string {
  if (count === 1) return '1 produkt';
  if (count >= 2 && count <= 4) return `${count} produkty`;
  return `${count} produktów`;
}
