import React, { useState, useMemo } from 'react';
import { Play, Trash2 } from 'lucide-react';

interface UserBatchFormProps {
  onSubmit: (userIds: number[]) => void;
  loading: boolean;
  onClear: () => void;
}

export const UserBatchForm: React.FC<UserBatchFormProps> = ({ onSubmit, loading, onClear }) => {
  const [inputValue, setInputValue] = useState('1, 2, 3, 4, 999');

  const parsedIds = useMemo(() => {
    const rawTokens = inputValue.split(/[\s,;\n]+/);
    const numbers: number[] = [];
    for (const token of rawTokens) {
      const trimmed = token.trim();
      if (trimmed) {
        const num = Number(trimmed);
        if (Number.isInteger(num) && num > 0) {
          numbers.push(num);
        }
      }
    }
    return Array.from(new Set(numbers));
  }, [inputValue]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (parsedIds.length === 0 || loading) return;
    onSubmit(parsedIds);
  };

  const isExceeded = parsedIds.length > 100;
  const isEmpty = parsedIds.length === 0;

  return (
    <div className="form-panel">
      <div className="form-panel-header">
        <span className="form-panel-title">Parâmetros de Execução do Lote</span>
        <span className="form-endpoint-tag">POST /api/users/fetch</span>
      </div>

      <form onSubmit={handleSubmit}>
        <div>
          <textarea
            id="user-ids-input"
            className="textarea-control"
            rows={3}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Informe os IDs numéricos separados por vírgula, espaço ou quebra de linha (ex: 1, 2, 3, 4, 999)..."
            disabled={loading}
          />
        </div>

        <div className="form-meta-row">
          <div className="chips-wrapper">
            <span className="chips-label">Cenários de teste:</span>
            <button
              type="button"
              className="chip-btn"
              onClick={() => setInputValue('1, 2, 3, 4, 5')}
              disabled={loading}
            >
              Lote Básico (1-5)
            </button>
            <button
              type="button"
              className="chip-btn"
              onClick={() => setInputValue('1, 2, 999, 1000')}
              disabled={loading}
            >
              Cenário Misto (200 & 404)
            </button>
            <button
              type="button"
              className="chip-btn"
              onClick={() => setInputValue('1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12')}
              disabled={loading}
            >
              Alta Concorrência (12 IDs)
            </button>
          </div>

          <div className="token-counter">
            IDs válidos: <strong>{parsedIds.length}</strong> / 100
            {isExceeded && <span className="text-danger ml-2">(Limite excedido)</span>}
          </div>
        </div>

        <div className="form-button-row">
          <button
            type="submit"
            className="btn-primary"
            disabled={loading || isEmpty || isExceeded}
          >
            {loading ? (
              <>
                <span className="spinner-sm" />
                <span>Processando lote...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Consultar Lote</span>
              </>
            )}
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setInputValue('');
              onClear();
            }}
            disabled={loading}
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Limpar</span>
          </button>
        </div>
      </form>
    </div>
  );
};
