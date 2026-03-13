import { API_BASE } from '@/lib/constants';
import type { MenuResponse } from '@/generated/api-types';
import RestaurantDetailClient from './RestaurantDetailClient';

interface RestaurantPageProps {
  params: { city: string; slug: string };
}

async function fetchMenu(restaurantId: string): Promise<MenuResponse | null> {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';
  try {
    const response = await fetch(`${baseUrl}${API_BASE}/restaurants/${restaurantId}/menu`, {
      next: { revalidate: 900 },
    });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

export default async function RestaurantPage({ params }: RestaurantPageProps) {
  const menu = await fetchMenu(params.slug);

  return (
    <RestaurantDetailClient
      city={params.city}
      restaurantId={params.slug}
      initialMenu={menu}
    />
  );
}
