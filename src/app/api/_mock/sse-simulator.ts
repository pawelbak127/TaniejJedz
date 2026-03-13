import { COMPARISON_RESULT_REST_001, type Platform } from './fixtures';
import { sleep } from './delays';

type SSESendFn = (event: string, data: Record<string, unknown>) => void;

export type SSEScenario = 'happy' | 'timeout' | 'partial' | 'all_fail' | 'slow' | 'instant';

export async function simulateSSE(send: SSESendFn, scenario: SSEScenario = 'happy') {
  switch (scenario) {
    case 'happy':
      return simulateHappyPath(send);
    case 'timeout':
      return simulateTimeout(send);
    case 'partial':
      return simulatePartial(send);
    case 'all_fail':
      return simulateAllFail(send);
    case 'slow':
      return simulateSlow(send);
    case 'instant':
      return simulateInstant(send);
    default:
      return simulateHappyPath(send);
  }
}

async function simulateHappyPath(send: SSESendFn) {
  // Wolt: fast cache hit (500ms)
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

  // Glovo: unavailable
  send('platform_status', {
    event: 'platform_status',
    platform: 'glovo',
    status: 'error',
  });

  // Final: comparison ready
  await sleep(300);
  send('comparison_ready', {
    event: 'ready',
    cheapest_open: 'pyszne',
    savings_grosz: 3800,
    savings_display: 'Zaoszczędź 38,00 zł na Pyszne.pl!',
  });
}

async function simulateTimeout(send: SSESendFn) {
  // Only Wolt responds
  await sleep(500);
  send('platform_status', {
    event: 'platform_status',
    platform: 'wolt',
    status: 'cached',
    age_seconds: 45,
    data: COMPARISON_RESULT_REST_001.wolt,
  });

  // Pyszne: fetching but never finishes
  await sleep(500);
  send('platform_status', {
    event: 'platform_status',
    platform: 'pyszne',
    status: 'fetching',
  });

  // UberEats: fetching but never finishes
  await sleep(500);
  send('platform_status', {
    event: 'platform_status',
    platform: 'ubereats',
    status: 'fetching',
  });

  // Glovo: error
  send('platform_status', {
    event: 'platform_status',
    platform: 'glovo',
    status: 'error',
  });

  // Timeout after 8s (shortened for dev)
  await sleep(6000);
  send('platform_status', {
    event: 'platform_status',
    platform: 'pyszne',
    status: 'timeout',
  });
  send('platform_status', {
    event: 'platform_status',
    platform: 'ubereats',
    status: 'timeout',
  });

  send('timeout', { event: 'timeout' });
}

async function simulatePartial(send: SSESendFn) {
  // Wolt: cached
  await sleep(300);
  send('platform_status', {
    event: 'platform_status',
    platform: 'wolt',
    status: 'cached',
    age_seconds: 120,
    data: COMPARISON_RESULT_REST_001.wolt,
  });

  // Pyszne: ready
  await sleep(1500);
  send('platform_status', {
    event: 'platform_status',
    platform: 'pyszne',
    status: 'ready',
    data: COMPARISON_RESULT_REST_001.pyszne,
  });

  // UberEats: error
  await sleep(500);
  send('platform_status', {
    event: 'platform_status',
    platform: 'ubereats',
    status: 'error',
  });

  // Glovo: closed
  send('platform_status', {
    event: 'platform_status',
    platform: 'glovo',
    status: 'closed',
    next_open: '18:00',
  });

  await sleep(300);
  send('comparison_ready', {
    event: 'ready',
    cheapest_open: 'pyszne',
    savings_grosz: 700,
    savings_display: 'Zaoszczędź 7,00 zł na Pyszne.pl!',
  });
}

async function simulateAllFail(send: SSESendFn) {
  const platforms: Platform[] = ['pyszne', 'wolt', 'ubereats', 'glovo'];

  for (const platform of platforms) {
    await sleep(500);
    send('platform_status', {
      event: 'platform_status',
      platform,
      status: 'fetching',
    });
  }

  await sleep(2000);

  for (const platform of platforms) {
    send('platform_status', {
      event: 'platform_status',
      platform,
      status: 'error',
    });
  }

  await sleep(300);
  send('comparison_ready', {
    event: 'ready',
    cheapest_open: null,
    savings_grosz: 0,
    savings_display: '',
  });
}

async function simulateSlow(send: SSESendFn) {
  // Everything takes 3-4s each
  await sleep(3000);
  send('platform_status', {
    event: 'platform_status',
    platform: 'wolt',
    status: 'ready',
    data: COMPARISON_RESULT_REST_001.wolt,
  });

  await sleep(3500);
  send('platform_status', {
    event: 'platform_status',
    platform: 'pyszne',
    status: 'ready',
    data: COMPARISON_RESULT_REST_001.pyszne,
  });

  await sleep(4000);
  send('platform_status', {
    event: 'platform_status',
    platform: 'ubereats',
    status: 'ready',
    data: COMPARISON_RESULT_REST_001.ubereats,
  });

  send('platform_status', {
    event: 'platform_status',
    platform: 'glovo',
    status: 'error',
  });

  await sleep(300);
  send('comparison_ready', {
    event: 'ready',
    cheapest_open: 'pyszne',
    savings_grosz: 3800,
    savings_display: 'Zaoszczędź 38,00 zł na Pyszne.pl!',
  });
}

async function simulateInstant(send: SSESendFn) {
  // All from cache in <200ms total
  await sleep(50);
  send('platform_status', {
    event: 'platform_status',
    platform: 'wolt',
    status: 'cached',
    age_seconds: 10,
    data: COMPARISON_RESULT_REST_001.wolt,
  });

  await sleep(50);
  send('platform_status', {
    event: 'platform_status',
    platform: 'pyszne',
    status: 'cached',
    age_seconds: 15,
    data: COMPARISON_RESULT_REST_001.pyszne,
  });

  await sleep(50);
  send('platform_status', {
    event: 'platform_status',
    platform: 'ubereats',
    status: 'cached',
    age_seconds: 20,
    data: COMPARISON_RESULT_REST_001.ubereats,
  });

  send('platform_status', {
    event: 'platform_status',
    platform: 'glovo',
    status: 'error',
  });

  await sleep(50);
  send('comparison_ready', {
    event: 'ready',
    cheapest_open: 'pyszne',
    savings_grosz: 3800,
    savings_display: 'Zaoszczędź 38,00 zł na Pyszne.pl!',
  });
}
