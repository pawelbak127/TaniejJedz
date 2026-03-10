import { NextRequest, NextResponse } from 'next/server';

const DEEP_LINKS: Record<string, string> = {
  pyszne: "https://www.pyszne.pl/menu/pizzeria-roma",
  wolt: "https://wolt.com/pl/pol/warsaw/restaurant/pizzeria-roma",
  ubereats: "https://www.ubereats.com/pl/store/pizzeria-roma/abc123",
  glovo: "https://glovoapp.com/pl/pl/warszawa/pizzeria-roma/",
};

export async function GET(
  request: NextRequest,
  { params }: { params: { platform: string; id: string } }
) {
  const url = DEEP_LINKS[params.platform] || "https://taniejjedz.pl";
  
  // W produkcji: loguj affiliate click do bazy
  console.log(`[MOCK REDIRECT] ${params.platform}/${params.id} → ${url}`);
  
  return NextResponse.redirect(url, { status: 302 });
}