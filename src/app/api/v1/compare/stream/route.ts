import { NextRequest } from 'next/server';
import { COMPARISON_RESULT_REST_001 } from '@/app/api/_mock/fixtures';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const comparisonId = searchParams.get('id');
  
  if (!comparisonId) {
    return new Response('Missing comparison id', { status: 400 });
  }

  const encoder = new TextEncoder();
  
  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: any) => {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };
      
      // Symuluj SSE flow z realistycznymi opóźnieniami
      // Każda platforma "odpowiada" po innym czasie
      
      const scenario = searchParams.get('scenario') || 'happy';
      
      if (scenario === 'timeout') {
         // Wolt: szybki cache hit (500ms)
        await sleep(500);
        send('platform_status', {
          event: 'platform_status',
          platform: 'wolt',
          status: 'cached',
          age_seconds: 45,
          data: COMPARISON_RESULT_REST_001.wolt,
        });
        
        // Symulacja przekroczenia czasu dla reszty
        await sleep(15000);
        send('timeout', { event: 'timeout' });
        controller.close();
        return;
      }

      if (scenario === 'all_fail') {
         await sleep(500);
         send('platform_status', { event: 'platform_status', platform: 'pyszne', status: 'error' });
         send('platform_status', { event: 'platform_status', platform: 'wolt', status: 'error' });
         send('platform_status', { event: 'platform_status', platform: 'ubereats', status: 'error' });
         send('platform_status', { event: 'platform_status', platform: 'glovo', status: 'error' });
         
         await sleep(300);
         send('comparison_ready', {
            event: 'ready',
            cheapest_open: null,
            savings_grosz: 0,
            savings_display: '',
         });
         controller.close();
         return;
      }

      // Default: happy path
      
      // Wolt: szybki cache hit (500ms)
      await sleep(500);
      send('platform_status', {
        event: 'platform_status',
        platform: 'wolt',
        status: 'cached',
        age_seconds: 45,
        data: COMPARISON_RESULT_REST_001.wolt,
      });
      
      // Pyszne: live fetch (1.5s)
      await sleep(1000);
      send('platform_status', {
        event: 'platform_status',
        platform: 'pyszne',
        status: 'fetching',
      });
      
      await sleep(1500);
      send('platform_status', {
        event: 'platform_status',
        platform: 'pyszne',
        status: 'ready',
        data: COMPARISON_RESULT_REST_001.pyszne,
      });
      
      // UberEats: slow fetch (3s)
      await sleep(500);
      send('platform_status', {
        event: 'platform_status',
        platform: 'ubereats',
        status: 'fetching',
      });
      
      await sleep(2500);
      send('platform_status', {
        event: 'platform_status',
        platform: 'ubereats',
        status: 'ready',
        data: COMPARISON_RESULT_REST_001.ubereats,
      });
      
      // Glovo: niedostępne
      send('platform_status', {
        event: 'platform_status',
        platform: 'glovo',
        status: 'error',
      });
      
      // Final: porównanie gotowe
      await sleep(300);
      send('comparison_ready', {
        event: 'ready',
        cheapest_open: 'pyszne',
        savings_grosz: 3800,
        savings_display: 'Zaoszczędź 38,00 zł na Pyszne.pl!',
      });
      
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}