import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { UserBatchForm } from '../components/UserBatchForm';
import { StatusBadge } from '../components/StatusBadge';
import { UserResultsTable } from '../components/UserResultsTable';
import App from '../App';
import { userService } from '../services/userService';

vi.mock('../services/userService', () => ({
  userService: {
    fetchUsersBatch: vi.fn(),
    checkHealth: vi.fn().mockResolvedValue({
      status: 'healthy',
      version: '1.0.0',
    }),
  },
}));

describe('UserBatchForm Component', () => {
  it('deve renderizar o textarea e botoes corretamente', () => {
    render(<UserBatchForm onSubmit={vi.fn()} loading={false} onClear={vi.fn()} />);

    expect(screen.getByPlaceholderText(/Informe os IDs numéricos/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Consultar Lote/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Limpar/i })).toBeInTheDocument();
  });

  it('deve fazer o parsing de IDs separados por virgula, espacos e quebras de linha', async () => {
    const handleSubmit = vi.fn();
    render(<UserBatchForm onSubmit={handleSubmit} loading={false} onClear={vi.fn()} />);

    const textarea = screen.getByPlaceholderText(/Informe os IDs numéricos/i);
    await userEvent.clear(textarea);
    await userEvent.type(textarea, '10, 20  30\n40; 50');

    const submitBtn = screen.getByRole('button', { name: /Consultar Lote/i });
    fireEvent.click(submitBtn);

    expect(handleSubmit).toHaveBeenCalledWith([10, 20, 30, 40, 50]);
  });

  it('deve preencher o textarea ao clicar nos chips de presets de teste', () => {
    render(<UserBatchForm onSubmit={vi.fn()} loading={false} onClear={vi.fn()} />);

    const chipBasico = screen.getByRole('button', { name: /Lote Básico/i });
    fireEvent.click(chipBasico);

    const textarea = screen.getByPlaceholderText(/Informe os IDs numéricos/i) as HTMLTextAreaElement;
    expect(textarea.value).toBe('1, 2, 3, 4, 5');

    const chipMisto = screen.getByRole('button', { name: /Cenário Misto/i });
    fireEvent.click(chipMisto);
    expect(textarea.value).toBe('1, 2, 999, 1000');

    const chipAlta = screen.getByRole('button', { name: /Alta Concorrência/i });
    fireEvent.click(chipAlta);
    expect(textarea.value).toContain('12');
  });

  it('deve desabilitar o botao de envio e exibir spinner enquanto loading for true', () => {
    render(<UserBatchForm onSubmit={vi.fn()} loading={true} onClear={vi.fn()} />);

    const submitBtn = screen.getByRole('button', { name: /Processando lote/i });
    expect(submitBtn).toBeDisabled();
  });

  it('deve limpar o campo e acionar onClear ao clicar no botao Limpar', () => {
    const handleClear = vi.fn();
    render(<UserBatchForm onSubmit={vi.fn()} loading={false} onClear={handleClear} />);

    const clearBtn = screen.getByRole('button', { name: /Limpar/i });
    fireEvent.click(clearBtn);

    const textarea = screen.getByPlaceholderText(/Informe os IDs numéricos/i) as HTMLTextAreaElement;
    expect(textarea.value).toBe('');
    expect(handleClear).toHaveBeenCalled();
  });
});

describe('StatusBadge Component (Painel de Falhas Isoladas)', () => {
  it('nao deve renderizar nada quando failedIds for vazio', () => {
    const { container } = render(<StatusBadge errors={[]} failedIds={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('deve renderizar falhas com status codes variados (404, 504, 429, 500)', () => {
    const errors = [
      { user_id: 404, status_code: 404, reason: 'Usuário não encontrado' },
      { user_id: 504, status_code: 504, reason: 'Timeout de gateway' },
      { user_id: 429, status_code: 429, reason: 'Rate limit excedido' },
      { user_id: 500, status_code: 500, reason: 'Internal server error' },
      { user_id: 502, status_code: 502, reason: 'Bad gateway' },
      { user_id: 999, status_code: null, reason: 'Erro de rede sem status' },
    ];
    render(<StatusBadge errors={errors} failedIds={[404, 504, 429, 500, 502, 999]} />);

    expect(screen.getByText(/Falhas de Consulta Isoladas \(6\)/i)).toBeInTheDocument();
    expect(screen.getByText('404 NOT FOUND')).toBeInTheDocument();
    expect(screen.getByText('504 TIMEOUT')).toBeInTheDocument();
    expect(screen.getByText('429 RATE LIMIT')).toBeInTheDocument();
    expect(screen.getByText('HTTP 502')).toBeInTheDocument();
    expect(screen.getByText('ERRO REDE')).toBeInTheDocument();
  });

  it('deve disparar onRetryFailed contendo exclusivamente os IDs que falharam', () => {
    const handleRetry = vi.fn();
    const errors = [{ user_id: 999, status_code: 404, reason: 'Not found' }];

    render(<StatusBadge errors={errors} failedIds={[999]} onRetryFailed={handleRetry} />);

    const retryBtn = screen.getByRole('button', { name: /Tentar novamente apenas estes IDs/i });
    fireEvent.click(retryBtn);

    expect(handleRetry).toHaveBeenCalledWith([999]);
  });
});

describe('UserResultsTable Component', () => {
  it('deve exibir mensagem de estado vazio quando lista de usuarios for vazia', () => {
    render(<UserResultsTable users={[]} />);
    expect(screen.getByText(/Nenhum usuário obtido neste lote/i)).toBeInTheDocument();
  });

  it('deve renderizar linhas de usuarios e o badge de Cache', () => {
    const users = [
      {
        id: 1,
        name: 'Ada Lovelace',
        username: 'ada',
        email: 'ada@example.com',
        company_name: 'Babbage Inc',
        website: 'https://ada.org',
        cached: true,
      },
      {
        id: 2,
        name: 'Charles Babbage',
        email: '',
        website: '',
        cached: false,
      },
    ];

    render(<UserResultsTable users={users} />);

    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('Charles Babbage')).toBeInTheDocument();
    expect(screen.getByText(/⚡ Cache/i)).toBeInTheDocument();
    expect(screen.getByText('Babbage Inc')).toBeInTheDocument();
    expect(screen.getByText('@ada')).toBeInTheDocument();
  });

  it('deve copiar o ID para a area de transferencia ao clicar no botao ID', async () => {
    const users = [{ id: 42, name: 'Douglas Adams', cached: false }];
    render(<UserResultsTable users={users} />);

    const copyBtn = screen.getByRole('button', { name: /ID/i });
    fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('42');
    await waitFor(() => {
      expect(screen.getByText('Copiado')).toBeInTheDocument();
    });
  });

  it('deve copiar todos os usuarios em JSON ao clicar no botao Copiar JSON', async () => {
    const users = [{ id: 1, name: 'User 1', cached: false }];
    render(<UserResultsTable users={users} />);

    const copyJsonBtn = screen.getByRole('button', { name: /Copiar JSON/i });
    fireEvent.click(copyJsonBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByText('JSON Copiado')).toBeInTheDocument();
    });
  });

  it('deve acionar download de CSV ao clicar no botao Baixar CSV', () => {
    const users = [
      {
        id: 1,
        name: 'User 1',
        username: 'u1',
        email: 'u1@test.com',
        company_name: 'Corp',
        website: 'corp.com',
        cached: false,
      },
    ];
    render(<UserResultsTable users={users} />);

    const downloadBtn = screen.getByRole('button', { name: /Baixar CSV/i });
    fireEvent.click(downloadBtn);

    expect(window.URL.createObjectURL).toHaveBeenCalled();
  });
});

describe('App Component (Integracao de Tela e Abas)', () => {
  it('deve renderizar o cabecalho e KPIs iniciais', () => {
    render(<App />);
    expect(screen.getByText(/Console de Usuários em Lote/i)).toBeInTheDocument();
    expect(screen.getByText(/Lote Solicitado/i)).toBeInTheDocument();
    expect(screen.getByText(/Sucessos/i)).toBeInTheDocument();
    expect(screen.getByText(/Falhas Isoladas/i)).toBeInTheDocument();
    expect(screen.getByText(/Cache Hits/i)).toBeInTheDocument();
  });

  it('deve alternar entre as abas e exibir a tabela e o painel de falhas', async () => {
    vi.mocked(userService.fetchUsersBatch).mockResolvedValueOnce({
      users: [{ id: 1, name: 'Linus Torvalds', cached: false }],
      failed: [999],
      errors: [{ user_id: 999, status_code: 404, reason: 'Nao encontrado' }],
      meta: {
        total: 2,
        success_count: 1,
        failed_count: 1,
        cache_hits: 0,
        execution_time_ms: 25.4,
      },
    });

    render(<App />);

    const submitBtn = screen.getByRole('button', { name: /Consultar Lote/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Linus Torvalds')).toBeInTheDocument();
    });

    // Clica na aba Usuários Obtidos
    const tabSuccess = screen.getByRole('button', { name: /Usuários Obtidos/i });
    fireEvent.click(tabSuccess);
    expect(screen.getByText('Linus Torvalds')).toBeInTheDocument();

    // Clica na aba Falhas Isoladas
    const tabFailed = screen.getByRole('button', { name: /Falhas Isoladas/i });
    fireEvent.click(tabFailed);
    expect(screen.getByText(/Falhas de Consulta Isoladas \(1\)/i)).toBeInTheDocument();

    // Clica na aba JSON Bruto
    const tabRaw = screen.getByRole('button', { name: /JSON Bruto/i });
    fireEvent.click(tabRaw);
    expect(screen.getByText(/"success_count": 1/i)).toBeInTheDocument();
  });
});
