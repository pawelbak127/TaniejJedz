import { API_BASE } from '@/lib/constants';
import type {
  SearchRequest,
  SearchResponse,
  MenuResponse,
  CompareRequest,
  CompareResponse,
  FeedbackRequest,
  ApiError,
} from '@/generated/api-types';

class ApiClientError extends Error {
  code: string;
  retry: boolean;
  status: number;

  constructor(status: number, error: ApiError['error']) {
    super(error.message);
    this.name = 'ApiClientError';
    this.code = error.code;
    this.retry = error.retry;
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let errorBody: ApiError;
    try {
      errorBody = await response.json();
    } catch {
      throw new ApiClientError(response.status, {
        code: 'UNKNOWN',
        message: `Błąd serwera (${response.status})`,
        retry: true,
      });
    }

    throw new ApiClientError(response.status, errorBody.error);
  }

  return response.json();
}

export const apiClient = {
  search(params: SearchRequest): Promise<SearchResponse> {
    return request<SearchResponse>('/search', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  getMenu(restaurantId: string): Promise<MenuResponse> {
    return request<MenuResponse>(`/restaurants/${restaurantId}/menu`);
  },

  startComparison(params: CompareRequest): Promise<CompareResponse> {
    return request<CompareResponse>('/compare', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  submitFeedback(params: FeedbackRequest): Promise<{ id: string; message: string }> {
    return request<{ id: string; message: string }>('/feedback', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  getRedirectUrl(platform: string, restaurantId: string, sessionId: string): string {
    return `${API_BASE}/redirect/${platform}/${restaurantId}?session=${sessionId}`;
  },
};

export { ApiClientError };
