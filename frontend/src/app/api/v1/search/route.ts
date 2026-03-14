import { NextRequest, NextResponse } from 'next/server';
import { RESTAURANTS } from '@/app/api/_mock/fixtures';

export async function POST(request: NextRequest) {
  await new Promise(r => setTimeout(r, 300 + Math.random() * 400));

  const body = await request.json();

  let results = [...RESTAURANTS];

  // Cuisine filter
  if (body.cuisine_filter?.length) {
    results = results.filter(r =>
      r.cuisine_tags.some((t: string) => body.cuisine_filter.includes(t))
    );
  }

  // "Open only" filter
  if (!body.show_closed) {
    results = results.filter(r => r.cheapest_open_platform !== null);
  }

  // Sorting
  if (body.sort_by === "cheapest_delivery") {
    results.sort((a, b) => (a.cheapest_delivery_fee_grosz ?? 9999) - (b.cheapest_delivery_fee_grosz ?? 9999));
  } else if (body.sort_by === "rating") {
    results.sort((a, b) => {
      const aMax = Math.max(...Object.values(a.platforms).map(p => p.rating ?? 0));
      const bMax = Math.max(...Object.values(b.platforms).map(p => p.rating ?? 0));
      return bMax - aMax;
    });
  }

  // Pagination
  const page = body.page || 1;
  const per_page = body.per_page || 20;
  const start = (page - 1) * per_page;
  const paginated = results.slice(start, start + per_page);

  return NextResponse.json({
    restaurants: paginated,
    total: results.length,
    page,
    per_page,
    city: "warszawa",
    data_freshness: {
      pyszne: { checked_at: new Date().toISOString(), is_live: true },
      wolt: { checked_at: new Date().toISOString(), is_live: true },
      ubereats: { checked_at: new Date(Date.now() - 120000).toISOString(), is_live: false },
      glovo: { checked_at: new Date(Date.now() - 300000).toISOString(), is_live: false },
    },
  });
}
