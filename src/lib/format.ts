/**
 * Formats a given price in grosze to a Polish currency string.
 * Ensures conversion from integer to standard decimal representation.
 */
export function formatPrice(grosz: number): string {
  return new Intl.NumberFormat('pl-PL', {
    style: 'currency',
    currency: 'PLN',
  }).format(grosz / 100);
}

/**
 * Formats an ISO date string to a relative time string (e.g., "5 min temu").
 */
export function formatRelativeTime(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) return 'przed chwilą';
  
  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) return `${diffInMinutes} min temu`;
  
  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) {
    if (diffInHours === 1) return '1 godzinę temu';
    if (diffInHours >= 2 && diffInHours <= 4) return `${diffInHours} godziny temu`;
    return `${diffInHours} godzin temu`;
  }
  
  return date.toLocaleDateString('pl-PL');
}