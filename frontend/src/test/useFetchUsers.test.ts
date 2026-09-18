import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFetchUsers } from '../hooks/useFetchUsers';
import { userService } from '../services/userService';
import { UserBatchResponse } from '../types/user';

vi.mock('../services/userService', () => ({
  userService: {
    fetchUsersBatch: vi.fn(),
    checkHealth: vi.fn(),
  },
}));

describe('useFetchUsers Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(userService.checkHealth).mockResolvedValue({
      status: 'healthy',
      service: 'Hit Digital',
      version: '1.0.0',
      environment: 'test',
      concurrency_limit: 10,
    });
  });

  it('deve inicializar com o estado padrao correto', async () => {
    const { result } = renderHook(() => useFetchUsers());

    expect(result.current.loading).toBe(false);
    expect(result.current.users).toEqual([]);
    expect(result.current.failedIds).toEqual([]);
    expect(result.current.errors).toEqual([]);
    expect(result.current.meta).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isBackendOnline).toBe(true);
  });

  it('deve rejeitar lista vazia com erro amigavel sem chamar a API', async () => {
    const { result } = renderHook(() => useFetchUsers());

    await act(async () => {
      await result.current.fetchUsers([]);
    });

    expect(result.current.error).toBe('Por favor, informe ao menos um ID de usuário.');
    expect(userService.fetchUsersBatch).not.toHaveBeenCalled();
  });

  it('deve atualizar o estado com sucesso quando o lote for consultado', async () => {
    const mockResponse: UserBatchResponse = {
      users: [
        {
          id: 1,
          name: 'Ada Lovelace',
          username: 'ada',
          email: 'ada@example.com',
          company_name: 'Analytical Engine',
          cached: false,
        },
      ],
      failed: [],
      errors: [],
      meta: {
        total: 1,
        success_count: 1,
        failed_count: 0,
        cache_hits: 0,
        execution_time_ms: 12.5,
      },
    };

    vi.mocked(userService.fetchUsersBatch).mockResolvedValueOnce(mockResponse);

    const { result } = renderHook(() => useFetchUsers());

    await act(async () => {
      await result.current.fetchUsers([1]);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.users).toHaveLength(1);
    expect(result.current.users[0].name).toBe('Ada Lovelace');
    expect(result.current.failedIds).toEqual([]);
    expect(result.current.errors).toEqual([]);
    expect(result.current.meta?.total).toBe(1);
    expect(result.current.error).toBeNull();
  });

  it('deve suportar falhas parciais populando users e failedIds simultaneamente', async () => {
    const mockResponse: UserBatchResponse = {
      users: [
        {
          id: 1,
          name: 'Alan Turing',
          cached: true,
        },
      ],
      failed: [999],
      errors: [
        {
          user_id: 999,
          status_code: 404,
          reason: 'Usuário com ID 999 não encontrado',
        },
      ],
      meta: {
        total: 2,
        success_count: 1,
        failed_count: 1,
        cache_hits: 1,
        execution_time_ms: 30.0,
      },
    };

    vi.mocked(userService.fetchUsersBatch).mockResolvedValueOnce(mockResponse);

    const { result } = renderHook(() => useFetchUsers());

    await act(async () => {
      await result.current.fetchUsers([1, 999]);
    });

    expect(result.current.users).toHaveLength(1);
    expect(result.current.failedIds).toEqual([999]);
    expect(result.current.errors).toHaveLength(1);
    expect(result.current.meta?.failed_count).toBe(1);
  });

  it('deve tratar erro catastrofico de conexao (status 0) e marcar backend como offline', async () => {
    const errorObj = {
      name: 'ApiError',
      message: 'Falha de conexão com a API. Verifique se o backend está em execução.',
      status: 0,
    };
    vi.mocked(userService.fetchUsersBatch).mockRejectedValueOnce(errorObj);

    const { result } = renderHook(() => useFetchUsers());

    await act(async () => {
      await result.current.fetchUsers([1]);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.error).toContain('Falha de conexão com a API');
    expect(result.current.isBackendOnline).toBe(false);
  });

  it('deve resetar todos os estados de dados ao chamar reset()', async () => {
    const mockResponse: UserBatchResponse = {
      users: [{ id: 1, name: 'User 1', cached: false }],
      failed: [2],
      errors: [{ user_id: 2, status_code: 500, reason: 'Error' }],
      meta: { total: 2, success_count: 1, failed_count: 1, cache_hits: 0, execution_time_ms: 10 },
    };
    vi.mocked(userService.fetchUsersBatch).mockResolvedValueOnce(mockResponse);

    const { result } = renderHook(() => useFetchUsers());

    await act(async () => {
      await result.current.fetchUsers([1, 2]);
    });

    expect(result.current.users).toHaveLength(1);
    expect(result.current.failedIds).toHaveLength(1);

    act(() => {
      result.current.reset();
    });

    expect(result.current.users).toEqual([]);
    expect(result.current.failedIds).toEqual([]);
    expect(result.current.errors).toEqual([]);
    expect(result.current.meta).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('deve atualizar o estado de saude na checagem periodica quando backend estiver offline', async () => {
    vi.mocked(userService.checkHealth).mockRejectedValue(new Error('Network Down'));

    const { result } = renderHook(() => useFetchUsers());

    await act(async () => {
      await result.current.checkBackend();
    });

    expect(result.current.isBackendOnline).toBe(false);
    expect(result.current.systemHealth).toBeNull();
  });
});
