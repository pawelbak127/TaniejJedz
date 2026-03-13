import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  await new Promise(r => setTimeout(r, 300));

  const body = await request.json();

  console.log('[MOCK FEEDBACK]', JSON.stringify(body, null, 2));

  return NextResponse.json({
    id: `fb-${Date.now()}`,
    message: "Dziękujemy za zgłoszenie! Sprawdzimy to.",
  });
}
