import type { Metadata } from 'next';
import { API_BASE, SUPPORTED_CITIES_DISPLAY } from '@/lib/constants';
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

export async function generateMetadata({ params }: RestaurantPageProps): Promise<Metadata> {
  const menu = await fetchMenu(params.slug);
  const cityDisplay = SUPPORTED_CITIES_DISPLAY[params.city] || params.city;

  if (!menu) {
    return {
      title: `Restauracja — ${cityDisplay}`,
      description: `Porównaj ceny dostaw w ${cityDisplay} na TaniejJedz.pl`,
    };
  }

  const platformCount = menu.restaurant.platforms_available.length;
  return {
    title: `${menu.restaurant.name} — porównaj ceny na ${platformCount} platformach`,
    description: `Porównaj ceny ${menu.restaurant.name} na Pyszne.pl, Uber Eats, Wolt i Glovo. Sprawdź, gdzie zamówisz taniej w ${cityDisplay}.`,
  };
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
