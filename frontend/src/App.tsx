import React, { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Code2,
  ListFilter,
  XCircle,
} from 'lucide-react';
import { StatusBadge } from './components/StatusBadge';
import { UserBatchForm } from './components/UserBatchForm';
import { UserResultsTable } from './components/UserResultsTable';
import { useFetchUsers } from './hooks/useFetchUsers';

type ActiveTab = 'all' | 'success' | 'failed' | 'raw';

export const App: React.FC = () => {
  const {
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
  } = useFetchUsers();

  const [activeTab, setActiveTab] = useState<ActiveTab>('all');

  const handleRetryFailed = (ids: number[]) => {
    fetchUsers(ids);
  };

  const hasExecuted = meta !== null;

  return (
    <main className="app-container">
      {/* 1. Header & Navigation */}
      <header className="header-bar">
        <div>
          <nav className="breadcrumb-nav" aria-label="Navegação estrutural">
            <span>Integrações</span>
            <span className="breadcrumb-separator">/</span>
            <span>Provedores Externos</span>
            <span className="breadcrumb-separator">/</span>
            <span style={{ color: 'var(--text-secondary)' }}>Consulta em Lote</span>
          </nav>
          <h1 className="header-title">Console de Usuários em Lote</h1>
        </div>

        <div className="header-status-indicator">
          <span className={`status-dot ${isBackendOnline ? 'online' : 'offline'}`} />
          <span>
            {isBackendOnline
              ? `API Conectada • FastAPI ${systemHealth ? `v${systemHealth.version}` : 'v1'}`
              : 'API Indisponível'}
          </span>
        </div>
      </header>

      {/* Banner de Erro Global */}
      {error && (
        <div className="corporate-error-banner" role="alert">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle className="w-4 h-4" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* 2. Barra Compacta de Métricas (KPIs) */}
      <section className="kpi-bar" aria-label="Métricas de execução do lote">
        <div className="kpi-item">
          <div className="kpi-label">Lote Solicitado</div>
          <div className="kpi-value-row">
            <span className="kpi-value">{meta ? meta.total : '0'}</span>
            <span className="kpi-badge neutral">IDs únicos</span>
          </div>
        </div>

        <div className="kpi-item">
          <div className="kpi-label">Sucessos</div>
          <div className="kpi-value-row">
            <span className="kpi-value">{meta ? meta.success_count : '0'}</span>
            <span className="kpi-badge success">Obtidos</span>
          </div>
        </div>

        <div className="kpi-item">
          <div className="kpi-label">Falhas Isoladas</div>
          <div className="kpi-value-row">
            <span className="kpi-value">{meta ? meta.failed_count : '0'}</span>
            <span className={`kpi-badge ${failedIds.length > 0 ? 'danger' : 'neutral'}`}>
              Não afetou lote
            </span>
          </div>
        </div>

        <div className="kpi-item">
          <div className="kpi-label">Cache Hits</div>
          <div className="kpi-value-row">
            <span className="kpi-value">{meta ? meta.cache_hits : '0'}</span>
            <span className="kpi-badge" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24' }}>
              TTL 60s
            </span>
          </div>
        </div>

        <div className="kpi-item">
          <div className="kpi-label">Tempo Total de Execução</div>
          <div className="kpi-value-row">
            <span className="kpi-value">
              {meta ? `${meta.execution_time_ms} ms` : '-'}
            </span>
          </div>
        </div>
      </section>

      {/* 3. Formulário de Entrada */}
      <UserBatchForm
        onSubmit={fetchUsers}
        loading={loading}
        onClear={reset}
      />

      {/* 4. Listagem de Resultados com Abas */}
      {hasExecuted && (
        <section className="results-card" aria-label="Resultados da consulta">
          <div className="tab-nav-bar">
            <div className="tab-group">
              <button
                type="button"
                className={`tab-item ${activeTab === 'all' ? 'active' : ''}`}
                onClick={() => setActiveTab('all')}
              >
                <ListFilter className="w-3.5 h-3.5" />
                <span>Todos os Itens</span>
                <span className="tab-count-pill">{meta.total}</span>
              </button>

              <button
                type="button"
                className={`tab-item ${activeTab === 'success' ? 'active' : ''}`}
                onClick={() => setActiveTab('success')}
              >
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Usuários Obtidos</span>
                <span className="tab-count-pill">{users.length}</span>
              </button>

              <button
                type="button"
                className={`tab-item ${activeTab === 'failed' ? 'active' : ''}`}
                onClick={() => setActiveTab('failed')}
              >
                <XCircle className="w-3.5 h-3.5 text-rose-400" />
                <span>Falhas Isoladas</span>
                <span className="tab-count-pill">{failedIds.length}</span>
              </button>

              <button
                type="button"
                className={`tab-item ${activeTab === 'raw' ? 'active' : ''}`}
                onClick={() => setActiveTab('raw')}
              >
                <Code2 className="w-3.5 h-3.5" />
                <span>JSON Bruto</span>
              </button>
            </div>
          </div>

          {/* Conteúdo da Aba Selecionada */}
          <div className="tab-content-wrapper">
            {activeTab === 'all' && (
              <div>
                <StatusBadge
                  errors={errors}
                  failedIds={failedIds}
                  onRetryFailed={handleRetryFailed}
                  loading={loading}
                />
                <UserResultsTable users={users} />
              </div>
            )}

            {activeTab === 'success' && (
              <UserResultsTable users={users} />
            )}

            {activeTab === 'failed' && (
              failedIds.length > 0 ? (
                <StatusBadge
                  errors={errors}
                  failedIds={failedIds}
                  onRetryFailed={handleRetryFailed}
                  loading={loading}
                />
              ) : (
                <div className="empty-tab-view">
                  <p>Nenhuma falha registrada neste lote.</p>
                </div>
              )
            )}

            {activeTab === 'raw' && (
              <pre className="json-viewer">
                {JSON.stringify(
                  {
                    users,
                    failed: failedIds,
                    errors,
                    meta,
                  },
                  null,
                  2
                )}
              </pre>
            )}
          </div>
        </section>
      )}

      {/* 5. Footer Corporativo */}
      <footer className="footer-corporate">
        <span>Sistema de Processamento Assíncrono Concorrente • Provedor: HTTP Rest Adapter</span>
        <span>Status do Cluster: Operacional</span>
      </footer>
    </main>
  );
};

export default App;
