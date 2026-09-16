import { useState, useCallback, useEffect } from 'react';
import { userService } from '../services/userService';
import { BatchMetadata, FailedUserDetail, SystemHealth, User, UserBatchResponse } from '../types/user';

export function useFetchUsers() {
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [failedIds, setFailedIds] = useState<number[]>([]);
  const [errors, setErrors] = useState<FailedUserDetail[]>([]);
  const [meta, setMeta] = useState<BatchMetadata | null>(null);

  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [isBackendOnline, setIsBackendOnline] = useState<boolean>(true);

  const checkBackend = useCallback(async () => {
    try {
      const health = await userService.checkHealth();
      setSystemHealth(health);
      setIsBackendOnline(true);
    } catch {
      setIsBackendOnline(false);
      setSystemHealth(null);
    }
  }, []);

  useEffect(() => {
    checkBackend();
    const interval = setInterval(checkBackend, 15000);
    return () => clearInterval(interval);
  }, [checkBackend]);

  const fetchUsers = useCallback(async (userIds: number[]) => {
    if (!userIds || userIds.length === 0) {
      setError('Por favor, informe ao menos um ID de usuário.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response: UserBatchResponse = await userService.fetchUsersBatch(userIds);
      setUsers(response.users);
      setFailedIds(response.failed);
      setErrors(response.errors);
      setMeta(response.meta);
      setIsBackendOnline(true);
    } catch (err: any) {
      const message = err.message || 'Ocorreu um erro ao comunicar com a API.';
      setError(message);
      if (err.status === 0) {
        setIsBackendOnline(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setUsers([]);
    setFailedIds([]);
    setErrors([]);
    setMeta(null);
    setError(null);
  }, []);

  return {
    loading,
    error,
    users,
    failedIds,
    errors,
    meta,
    fetchUsers,
    reset,
    systemHealth,
    isBackendOnline,
    checkBackend,
  };
}
