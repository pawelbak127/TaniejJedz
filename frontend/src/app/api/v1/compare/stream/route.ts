import { NextRequest } from 'next/server';
import { simulateSSE, type SSEScenario } from '@/app/api/_mock/sse-simulator';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const comparisonId = searchParams.get('id');

  if (!comparisonId) {
    return new Response('Missing comparison id', { status: 400 });
  }

  const scenario = (searchParams.get('scenario') || 'happy') as SSEScenario;
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: Record<string, unknown>) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };

      try {
        await simulateSSE(send, scenario);
      } catch {
        // Stream closed by client
      } finally {
        try {
          controller.close();
        } catch {
          // Already closed
        }
      }
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
