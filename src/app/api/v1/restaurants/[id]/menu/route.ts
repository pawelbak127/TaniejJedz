import { NextRequest, NextResponse } from 'next/server';
import { getMenuForRestaurant } from '@/app/api/_mock/fixtures';

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  await new Promise(r => setTimeout(r, 200 + Math.random() * 300));

  const menu = getMenuForRestaurant(params.id);

  if (!menu) {
    return NextResponse.json(
      { error: { code: "NOT_FOUND", message: "Restauracja nie znaleziona", retry: false } },
      { status: 404 }
    );
  }

  return NextResponse.json(menu);
}
