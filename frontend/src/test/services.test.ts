import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient, ApiError } from '../services/api';
import { userService } from '../services/userService';

describe('apiClient & userService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('deve realizar requisicao GET com sucesso e retornar dados parseados', async () => {
    const mockData = { status: 'healthy', version: '1.0.0' };
    const mockResponse = new Response(JSON.stringify(mockData), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(mockResponse);

    const result = await apiClient<typeof mockData>('/health');
    expect(result).toEqual(mockData);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/health'),
      expect.objectContaining({
        headers: expect.any(Headers),
      })
    );
  });

  it('deve realizar requisicao POST enviando body e headers corretos', async () => {
    const mockResponse = new Response(JSON.stringify({ users: [], failed: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(mockResponse);

    const payload = { user_ids: [1, 2] };
    const result = await userService.fetchUsersBatch([1, 2]);

    expect(result).toEqual({ users: [], failed: [] });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/users/fetch'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
      })
    );
  });

  it('deve chamar /health via userService.checkHealth', async () => {
    const mockHealth = {
      status: 'healthy',
      service: 'Hit Digital',
      version: '1.0.0',
      environment: 'development',
      concurrency_limit: 10,
    };
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockHealth), { status: 200 })
    );

    const res = await userService.checkHealth();
    expect(res).toEqual(mockHealth);
  });

  it('deve lancar ApiError com mensagem do detail quando a resposta for HTTP 422/404/500', async () => {
    const errorBody = { detail: 'A lista de IDs não pode ser vazia.' };
    const mockResponse = new Response(JSON.stringify(errorBody), {
      status: 422,
      statusText: 'Unprocessable Entity',
      headers: { 'Content-Type': 'application/json' },
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(mockResponse);

    await expect(apiClient('/api/users/fetch', { method: 'POST' })).rejects.toThrow(ApiError);
  });

  it('deve lancar ApiError com statusText quando body nao for JSON', async () => {
    const mockResponse = new Response('Bad Gateway', {
      status: 502,
      statusText: 'Bad Gateway',
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(mockResponse);

    try {
      await apiClient('/test-bad-gateway');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(502);
    }
  });

  it('deve tratar AbortError e lancar timeout 504', async () => {
    const abortErr = new Error('The operation was aborted');
    abortErr.name = 'AbortError';
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(abortErr);

    try {
      await apiClient('/timeout-test', { timeoutMs: 10 });
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(504);
      expect(err.message).toContain('Tempo limite excedido');
    }
  });

  it('deve tratar falha generica de rede e lancar status 0', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'));

    try {
      await apiClient('/network-error');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(0);
      expect(err.message).toBe('Failed to fetch');
    }
  });

  it('deve usar mensagem padrao quando o erro nao possuir message', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce({});

    try {
      await apiClient('/no-msg-error');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(0);
      expect(err.message).toContain('Falha de conexão com a API');
    }
  });
});
