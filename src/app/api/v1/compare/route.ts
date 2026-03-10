import { NextRequest, NextResponse } from 'next/server';

// Prosty in-memory store dla idempotency (w produkcji: Redis)
const idempotencyStore = new Map<string, string>();

export async function POST(request: NextRequest) {
  const body = await request.json();
  const idempotencyKey = request.headers.get('x-idempotency-key')
    || `${body.restaurant_id}-${JSON.stringify(body.items)}`;
  
  // Sprawdź idempotency
  const existing = idempotencyStore.get(idempotencyKey);
  if (existing) {
    return NextResponse.json({ comparison_id: existing, status: "already_processing" });
  }
  
  const comparisonId = `cmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  idempotencyStore.set(idempotencyKey, comparisonId);
  
  // Wyczyść po 60s
  setTimeout(() => idempotencyStore.delete(idempotencyKey), 60000);
  
  return NextResponse.json(
    { comparison_id: comparisonId, status: "processing" },
    { status: 202 }
  );
}