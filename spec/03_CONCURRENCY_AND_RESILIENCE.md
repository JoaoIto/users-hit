# 03. CONCORR?NCIA, SEM?FOROS E RESILI?NCIA ADAPTATIVA

Este documento analisa em profundidade a engenharia de concorr?ncia, o modelo operacional ass?ncrono e os padr?es de resili?ncia implementados no **Hit Digital - Async User Batch Fetcher**.

---

## 1. Modelo Ass?ncrono do Python em Workloads I/O-Bound

O processamento concorrente de requisi??es HTTP ? um caso can?nico de workload **I/O-Bound** (limitado por opera??es de entrada e sa?da de rede), onde a CPU despende a maior parte do ciclo ociosa, aguardando pacotes retornarem atrav?s dos sockets do kernel.

### 1.1 Tabela Comparativa de Modelos de Concorr?ncia em Python

| Dimens?o de Engenharia | `asyncio` (Corrotinas Cooperativas) | `Threading` (Threads do SO / `threading`) | `Multiprocessing` (Processos Isolados) |
| :--- | :--- | :--- | :--- |
| **Mecanismo de Execu??o** | Loop de eventos ?nico (Single-thread Event Loop) | M?ltiplas threads do SO (Kernel Threads) | M?ltiplos processos do SO (Fork/Spawn) |
| **Preemp??o vs. Coopera??o** | **Cooperativo** (chaveamento expl?cito com `await`) | Preemptivo (chaveamento for?ado pelo SO / GIL) | Preemptivo gerenciado pelo agendador do SO |
| **Impacto do GIL (Global Interpreter Lock)**| **Zero impacto** (o GIL ? liberado durante I/O) | Alto impacto em CPU; neutro em I/O puro | Zero impacto (cada processo tem seu pr?prio GIL)|
| **Consumo de Mem?ria por Tarefa** | **~2 KB** por corrotina (State Machine do gerador) | **~8 MB a 16 MB** (Stack reservada pelo SO) | **~30 MB a 60 MB** (Duplica??o do interpretador)|
| **Overhead de Context Switching** | **Extremamente baixo** (ordem de nanossegundos em user space) | Moderado a Alto (troca de contexto de kernel) | Muito Alto (troca de contexto e invalida??o de TLB)|
| **Concorr?ncia Suportada** | **10.000 a 100.000+** tarefas simult?neas | 500 a 2.000 threads (limite de mem?ria e thread contention)| Limitado ao n?mero de cores de CPU (4 a 64)|
| **Comunica??o entre Tarefas** | Mem?ria compartilhada nativa (sem locks pesados) | Mem?ria compartilhada (exige Locks, Mutexes) | IPC (Inter-Process Communication via Pipes/Sockets)|
| **Ader?ncia ao Desafio** | **Ideal (Arquitetura adotada)** | Inadequado (alto consumo e risco de race conditions)| Superdimensionado para I/O puro |

### 1.2 Por que Corrotinas Cooperativas Superam Threads
No `asyncio`, as corrotinas s?o fun??es geradoras paus?veis que cedem voluntariamente o controle da CPU atrav?s da palavra-chave `await`. Enquanto uma chamada de rede (`httpx.get`) aguarda a resposta dos servidores do JSONPlaceholder:
1. O socket de rede ? registrado no subsistema de polling do kernel do sistema operacional (`epoll` no Linux, `kqueue` no macOS, `IOCP` no Windows).
2. O Loop de Eventos avan?a imediatamente para processar a pr?xima corrotina da fila de prontos.
3. Quando a placa de rede recebe os pacotes TCP e o kernel sinaliza a conclus?o do descritor de arquivo, o Loop de Eventos retoma a corrotina no ponto exato onde foi suspensa.

Essa abordagem elimina a necessidade de pilhas de execu??o dedicadas do sistema operacional (*kernel stacks*), permitindo que a aplica??o gerencie centenas de requisi??es simult?neas utilizando menos de **50 MB de RAM**.

---

## 2. Governan?a de Concorr?ncia com `asyncio.Semaphore`

Disparar centenas de requisi??es simult?neas sem controle de fluxo ? uma receita cl?ssica para incidentes de produ??o. O `UserFetchService` implementa um mecanismo r?gido de estrangulamento (*throttling*) baseado em `asyncio.Semaphore`:

```text
Lote de Entrada: [ID_1, ID_2, ID_3, ..., ID_100]
                      |
                      v
             [asyncio.gather]
                      |
    +-----------------+-----------------+
    |        asyncio.Semaphore(10)      |
    |  [Slot 1]  [Slot 2] ... [Slot 10] |  <-- M?ximo de 10 chamadas ativas na rede
    +-----------------+-----------------+
                      |
    (Tarefas 11 a 100 aguardam na fila FIFO)
                      |
                      v
          [Rede / JSONPlaceholder]
```

### 2.1 Mecanismo Matem?tico e Operacional do Sem?foro
O sem?foro ass?ncrono gerencia um contador at?mico interno inicializado com `value = max_concurrency` (padr?o: 10).
- **Entrada (`async with self._semaphore`):**
  - Se `value > 0`, decrementa o contador em 1 (`value -= 1`) e permite que a corrotina prossiga imediatamente.
  - Se `value == 0`, a corrotina suspende sua execu??o e ingressa em uma fila interna `collections.deque` de tarefas em espera, cedendo a CPU.
- **Sa?da (Ao finalizar o bloco de contexto):**
  - Incrementa o contador (`value += 1`) e desperta imediatamente a pr?xima corrotina da fila FIFO.

### 2.2 Vetores de Falha Mitigados pelo Sem?foro
1. **Socket Exhaustion & File Descriptor Exhaustion (OS Limit):** Cada socket aberto consome um descritor de arquivos no sistema operacional (limite `ulimit -n` no Linux). Disparar 10.000 requisi??es simult?neas causaria `OSError: [Errno 24] Too many open files`. O sem?foro limita os descritores ativos a uma fra??o segura da capacidade do sistema.
2. **Prote??o contra Banimento por Rate Limit Remoto:** APIs p?blicas e servi?os de nuvem possuem firewalls de aplica??o (WAF) que bloqueiam rajadas abruptas (*bursts*) de tr?fego oriundas de um mesmo endere?o IP com erros `HTTP 429 Too Many Requests` ou bloqueio de firewall `HTTP 403 Forbidden`. O sem?foro suaviza a curva de tr?fego, transformando um ataque em potencial em um fluxo ordenado de requisi??es.

---

## 3. Resili?ncia Adaptativa e Tratamento Especializado de HTTP 429

A comunica??o com APIs remotas ? inerentemente inst?vel. O sistema implementa uma pol?tica de retry sofisticada e adaptativa em `backend/app/providers/external_user_provider.py` utilizando a biblioteca `tenacity`.

### 3.1 Classifica??o Estrita de Exce??es: Falhas Transit?rias vs. Falhas Fatais

Um erro comum em implementa??es amadoras de retry ? retentar requisi??es cegamente diante de qualquer erro. O sistema diferencia com precis?o matem?tica o que deve e o que **n?o deve** ser retentado:

```text
                             [Falha na Chamada HTTP]
                                        |
                   +--------------------+--------------------+
                   |                                         |
          [Falha Permanente]                        [Falha Transit?ria]
       (Ex.: HTTP 404 Not Found)              (Ex.: HTTP 429, 500, 503, Timeout)
                   |                                         |
                   v                                         v
         Levanta UserNotFoundError               Aplica Pol?tica de Retentativas
       SEM RETENTATIVA (Zero Wait)            (Tenacity Backoff com Jitter / Retry-After)
```

- **Falha Permanente (`UserNotFoundError`):**
  - Quando a API remota retorna `HTTP 404 Not Found`, significa que o recurso n?o existe na base de dados.
  - **Decis?o:** Retentar um 404 ? um desperd?cio de tempo e recursos de rede. A exce??o `UserNotFoundError` ? levantada imediatamente e exclu?da expressamente da tupla de retentativas do Tenacity (`retry_if_exception_type`).
- **Falhas Transit?rias (`ProviderServerError`, `ProviderTimeoutError`, `ProviderRateLimitError`):**
  - Instabilidades tempor?rias de roteamento, timeouts de socket e sobrecargas transit?rias de servidores de terceiros.
  - **Decis?o:** Retentar at? 3 vezes (`stop_after_attempt(3)`).

### 3.2 Estrat?gia Customizada `wait_retry_after_or_exponential`

Quando um servidor remoto ? sobrecarregado, ele emite o c?digo `HTTP 429 Too Many Requests` e frequentemente inclui o cabe?alho padronizado `Retry-After`, que informa em quantos segundos o cliente deve aguardar antes de tentar novamente. Ignorar esse cabe?alho e continuar disparando retentativas viola o protocolo de coopera??o da web e pode gerar banimento definitivo do IP.

O sistema implementa a classe `wait_retry_after_or_exponential` herdando de `tenacity.wait.wait_base`:

```python
# Refer?ncia: backend/app/providers/external_user_provider.py
class wait_retry_after_or_exponential(wait_base):
    def __init__(self, fallback_wait: wait_base, max_wait: float = 10.0):
        self.fallback_wait = fallback_wait
        self.max_wait = max_wait

    def __call__(self, retry_state: RetryCallState) -> float:
        if retry_state.outcome and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            # Se a falha foi por Rate Limit (HTTP 429) e veio com o cabe?alho Retry-After:
            if isinstance(exc, ProviderRateLimitError) and exc.retry_after is not None:
                # Respeita o cabe?alho do servidor remoto, limitado a um teto de seguran?a
                wait_time = min(float(exc.retry_after), self.max_wait)
                logger.info(
                    "tenacity_respecting_retry_after_header",
                    user_id=exc.user_id,
                    wait_seconds=wait_time,
                )
                return wait_time
        # Caso contr?rio, aplica o backoff exponencial com jitter padr?o
        return self.fallback_wait(retry_state)
```

### 3.3 Recuo Exponencial com Jitter (Randomized Exponential Backoff)
Para falhas onde o cabe?alho `Retry-After` n?o ? fornecido, a estrat?gia de fallback utiliza `wait_random_exponential(multiplier=0.5, max=2.0)`.

**Por que o Jitter Aleat?rio ? Essencial?**
Se 20 requisi??es simult?neas falharem ao mesmo tempo (ex.: o servidor remoto caiu momentaneamente) e todas aplicarem um recuo exponencial fixo (ex.: exatamente 1s, depois 2s), todas as 20 requisi??es disparar?o uma nova onda de choque simult?nea contra o servidor exatamente no mesmo instante (*efeito de manada* ou *thundering herd problem*).
O **Jitter** adiciona um ru?do pseudoaleat?rio ? equa??o de espera:
$$WaitTime = \min(MaxWait, Uniform(0, Multiplier \times 2^{attempt}))$$
Isso distribui uniformemente as retentativas no eixo temporal, permitindo que o servidor remoto se recupere sem ser bombardeado por picos s?ncronos de tr?fego.
