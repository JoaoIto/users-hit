import { apiClient } from './api';
import { SystemHealth, UserBatchResponse, UserFetchRequest } from '../types/user';

export const userService = {
  /**
   * Consulta um lote de IDs de usuários de forma concorrente e resiliente.
   */
  async fetchUsersBatch(userIds: number[]): Promise<UserBatchResponse> {
    const payload: UserFetchRequest = { user_ids: userIds };
    return apiClient<UserBatchResponse>('/api/users/fetch', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Verifica o estado de saúde do backend e limites de concorrência ativos.
   */
  async checkHealth(): Promise<SystemHealth> {
    return apiClient<SystemHealth>('/health', {
      method: 'GET',
      timeoutMs: 4000,
    });
  },
};
