import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { FailedUserDetail } from '../types/user';

interface StatusBadgeProps {
  errors: FailedUserDetail[];
  failedIds: number[];
  onRetryFailed?: (ids: number[]) => void;
  loading?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  errors,
  failedIds,
  onRetryFailed,
  loading = false,
}) => {
  if (!failedIds || failedIds.length === 0) {
    return null;
  }

  const getStatusClass = (statusCode?: number | null) => {
    if (statusCode === 404) return 'failure-badge code-404';
    if (statusCode === 504 || statusCode === 500) return 'failure-badge code-500';
    return 'failure-badge';
  };

  const getStatusLabel = (statusCode?: number | null) => {
    if (statusCode === 404) return '404 NOT FOUND';
    if (statusCode === 504) return '504 TIMEOUT';
    if (statusCode === 429) return '429 RATE LIMIT';
    if (statusCode) return `HTTP ${statusCode}`;
    return 'ERRO REDE';
  };

  return (
    <div className="failures-panel">
      <div className="failures-alert-header">
        <div className="failures-alert-title">
          <AlertCircle className="w-4 h-4" />
          <span>Falhas de Consulta Isoladas ({failedIds.length})</span>
        </div>

        {onRetryFailed && (
          <button
            type="button"
            className="btn-retry-failed"
            onClick={() => onRetryFailed(failedIds)}
            disabled={loading}
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
            <span>Tentar novamente apenas estes IDs ({failedIds.length})</span>
          </button>
        )}
      </div>

      <div className="failures-list">
        {errors.map((item) => (
          <div key={item.user_id} className="failure-item-row">
            <div className="failure-item-left">
              <span className="cell-id">ID #{item.user_id}</span>
              <span className={getStatusClass(item.status_code)}>
                {getStatusLabel(item.status_code)}
              </span>
              <span className="failure-reason">{item.reason}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
