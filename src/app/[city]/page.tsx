import type { Metadata } from 'next';
import { API_BASE, SUPPORTED_CITIES_DISPLAY } from '@/lib/constants';
import type { SearchResponse } from '@/generated/api-types';
import RestaurantListClient from './RestaurantListClient';

interface CityPageProps {
  params: { city: string };
}

export function generateMetadata({ params }: CityPageProps): Metadata {
  const cityDisplay = SUPPORTED_CITIES_DISPLAY[params.city] || params.city;
  return {
    title: `Restauracje w ${cityDisplay} — porównaj ceny dostaw`,
    description: `Porównaj ceny dostaw jedzenia w ${cityDisplay}. Sprawdź Pyszne.pl, Uber Eats, Wolt i Glovo — znajdź najtańszą dostawę.`,
  };
}

async function fetchInitialRestaurants(city: string): Promise<SearchResponse> {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';
  const response = await fetch(`${baseUrl}${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      address: city,
      latitude: 52.2297,
      longitude: 21.0122,
      show_closed: false,
      sort_by: 'relevance',
      page: 1,
      per_page: 20,
    }),
    next: { revalidate: 1800 },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch restaurants');
  }

  return response.json();
}

export default async function CityPage({ params }: CityPageProps) {
  let initialData: SearchResponse | null = null;

  try {
    initialData = await fetchInitialRestaurants(params.city);
  } catch {
    // Client component will handle error + retry
  }

  return (
    <RestaurantListClient
      city={params.city}
      initialRestaurants={initialData?.restaurants ?? []}
      initialTotal={initialData?.total ?? 0}
      fetchError={initialData === null}
    />
  );
}
