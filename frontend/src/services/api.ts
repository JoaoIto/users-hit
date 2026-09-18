const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 15000, ...customConfig } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  const headers = new Headers({
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...(customConfig.headers || {}),
  });

  try {
    const response = await fetch(url, {
      ...customConfig,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      let errorData: any;
      const rawText = await response.text();
      try {
        errorData = JSON.parse(rawText);
      } catch {
        errorData = rawText;
      }
      const message = errorData?.detail || errorData?.message || (typeof errorData === 'string' && errorData.trim() ? errorData : `Erro HTTP ${response.status}: ${response.statusText}`);
      throw new ApiError(message, response.status, errorData);
    }

    return (await response.json()) as T;
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new ApiError('Tempo limite excedido na comunicação com o servidor.', 504);
    }
    if (err instanceof ApiError || err?.name === 'ApiError') {
      throw err;
    }
    throw new ApiError(
      err.message || 'Falha de conexão com a API. Verifique se o backend está em execução.',
      0
    );
  }
}

export { API_BASE_URL };
