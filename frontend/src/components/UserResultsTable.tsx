import React, { useState } from 'react';
import { Check, Copy, Download, ExternalLink } from 'lucide-react';
import { User } from '../types/user';

interface UserResultsTableProps {
  users: User[];
}

export const UserResultsTable: React.FC<UserResultsTableProps> = ({ users }) => {
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [copiedAll, setCopiedAll] = useState<boolean>(false);

  const handleCopyId = (id: number) => {
    navigator.clipboard.writeText(String(id));
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(users, null, 2));
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), 2000);
  };

  const handleDownloadCsv = () => {
    if (users.length === 0) return;
    const headers = ['ID', 'Nome', 'Username', 'Email', 'Empresa', 'Website'];
    const rows = users.map((u) => [
      u.id,
      `"${u.name.replace(/"/g, '""')}"`,
      `"${(u.username || '').replace(/"/g, '""')}"`,
      `"${(u.email || '').replace(/"/g, '""')}"`,
      `"${(u.company_name || '').replace(/"/g, '""')}"`,
      `"${(u.website || '').replace(/"/g, '""')}"`,
    ]);
    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `usuarios_export_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (users.length === 0) {
    return (
      <div className="empty-tab-view">
        <p>Nenhum usuário obtido neste lote.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="tab-nav-bar" style={{ background: 'transparent', padding: '0.75rem 1rem' }}>
        <span className="text-tertiary" style={{ fontSize: '0.75rem' }}>
          Exibindo {users.length} {users.length === 1 ? 'registro' : 'registros'}
        </span>

        <div className="tab-actions">
          <button
            type="button"
            className="action-btn-sm"
            onClick={handleCopyJson}
            title="Copiar lista de usuários em JSON"
          >
            {copiedAll ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            <span>{copiedAll ? 'JSON Copiado' : 'Copiar JSON'}</span>
          </button>
          <button
            type="button"
            className="action-btn-sm"
            onClick={handleDownloadCsv}
            title="Exportar dados obtidos em arquivo CSV"
          >
            <Download className="w-3 h-3" />
            <span>Baixar CSV</span>
          </button>
        </div>
      </div>

      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '80px' }}>ID</th>
              <th>Nome Completo</th>
              <th>E-mail</th>
              <th>Empresa / Username</th>
              <th>Website</th>
              <th style={{ width: '100px', textAlign: 'right' }}>Ação</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td className="cell-id">#{user.id}</td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <span className="cell-name">{user.name}</span>
                    {user.cached && (
                      <span className="cell-cache-badge" title="Recuperado instantaneamente do TTL Cache em memória">
                        ⚡ Cache
                      </span>
                    )}
                  </div>
                </td>
                <td>
                  {user.email ? (
                    <a
                      href={`mailto:${user.email}`}
                      className="text-secondary hover:text-white"
                      style={{ textDecoration: 'none' }}
                    >
                      {user.email}
                    </a>
                  ) : (
                    <span className="text-tertiary">-</span>
                  )}
                </td>
                <td>
                  <div style={{ color: 'var(--text-primary)' }}>{user.company_name || '-'}</div>
                  {user.username && <div className="cell-subtext">@{user.username}</div>}
                </td>
                <td>
                  {user.website ? (
                    <a
                      href={user.website.startsWith('http') ? user.website : `https://${user.website}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-secondary hover:text-white"
                      style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                    >
                      <span>{user.website}</span>
                      <ExternalLink className="w-3 h-3 text-tertiary" />
                    </a>
                  ) : (
                    <span className="text-tertiary">-</span>
                  )}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button
                    type="button"
                    className="copy-id-btn"
                    onClick={() => handleCopyId(user.id)}
                    title="Copiar ID para a área de transferência"
                  >
                    {copiedId === user.id ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-400" />
                        <span>Copiado</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3" />
                        <span>ID</span>
                      </>
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
