# 3. Resiliência Adaptativa e Tratamento Especializado de HTTP 429

A comunicação com APIs remotas é inerentemente instável. O sistema implementa uma política de retry sofisticada e adaptativa em `backend/app/providers/external_user_provider.py` utilizando a biblioteca `tenacity`.

---

### Arquivo Completo (03. CONCORRÊNCIA, SEMÁFOROS E RESILIÊNCIA ADAPTATIVA)

Caso queira substituir o arquivo inteiro de uma só vez para evitar qualquer outro ponto corrompido:

```markdown
# 03. CONCORRÊNCIA, SEMÁFOROS E RESILIÊNCIA ADAPTATIVA

Este documento analisa em profundidade a engenharia de concorrência, o modelo operacional assíncrono e os padrões de resiliência implementados no **Hit Digital - Async User Batch Fetcher**.

---

## 1. Modelo Assíncrono do Python em Workloads I/O-Bound

O processamento concorrente de requisições HTTP é um caso canônico de workload **I/O-Bound** (limitado por operações de entrada e saída de rede), onde a CPU despende a maior parte do ciclo ociosa, aguardando pacotes retornarem através dos sockets do kernel.

### 1.1 Tabela Comparativa de Modelos de Concorrência em Python

| Dimensão de Engenharia | `asyncio` (Corrotinas Cooperativas) | `Threading` (Threads do SO / `threading`) | `Multiprocessing` (Processos Isolados) |
| :--- | :--- | :--- | :--- |
| **Mecanismo de Execução** | Loop de eventos único (Single-thread Event Loop) | Múltiplas threads do SO (Kernel Threads) | Múltiplos processos do SO (Fork/Spawn) |
| **Preempção vs. Cooperação** | **Cooperativo** (chaveamento explícito com `await`) | Preemptivo (chaveamento forçado pelo SO / GIL) | Preemptivo gerenciado pelo agendador do SO |
| **Impacto do GIL (Global Interpreter Lock)**| **Zero impacto** (o GIL é liberado durante I/O) | Alto impacto em CPU; neutro em I/O puro | Zero impacto (cada processo tem seu próprio GIL)|
| **Consumo de Memória por Tarefa** | **~2 KB** por corrotina (State Machine do gerador) | **~8 MB a 16 MB** (Stack reservada pelo SO) | **~30 MB a 60 MB** (Duplicação do interpretador)|
| **Overhead de Context Switching** | **Extremamente baixo** (ordem de nanossegundos em user space) | Moderado a Alto (troca de contexto de kernel) | Muito Alto (troca de contexto e invalidação de TLB)|
| **Concorrência Suportada** | **10.000 a 100.000+** tarefas simultâneas | 500 a 2.000 threads (limite de memória e thread contention)| Limitado ao número de cores de CPU (4 a 64)|
| **Comunicação entre Tarefas** | Memória compartilhada nativa (sem locks pesados) | Memória compartilhada (exige Locks, Mutexes) | IPC (Inter-Process Communication via Pipes/Sockets)|
| **Aderência ao Desafio** | **Ideal (Arquitetura adotada)** | Inadequado (alto consumo e risco de race conditions)| Superdimensionado para I/O puro |

### 1.2 Por que Corrotinas Cooperativas Superam Threads
No `asyncio`, as corrotinas são funções geradoras pausáveis que cedem voluntariamente o controle da CPU através da palavra-chave `await`. Enquanto uma chamada de rede (`httpx.get`) aguarda a resposta dos servidores do JSONPlaceholder:
1. O socket de rede é registrado no subsistema de polling do kernel do sistema operacional (`epoll` no Linux, `kqueue` no macOS, `IOCP` no Windows).
2. O Loop de Eventos avança imediatamente para processar a próxima corrotina da fila de prontos.
3. Quando a placa de rede recebe os pacotes TCP e o kernel sinaliza a conclusão do descritor de arquivo, o Loop de Eventos retoma a corrotina no ponto exato onde foi suspensa.

Essa abordagem elimina a necessidade de pilhas de execução dedicadas do sistema operacional (*kernel stacks*), permitindo que a aplicação gerencie centenas de requisições simultâneas utilizando menos de **50 MB de RAM**.

---

## 2. Governança de Concorrência com `asyncio.Semaphore`

Disparar centenas de requisições simultâneas sem controle de fluxo é uma receita clássica para incidentes de produção. O `UserFetchService` implementa um mecanismo rígido de estrangulamento (*throttling*) baseado em `asyncio.Semaphore`:

```text
Lote de Entrada: [ID_1, ID_2, ID_3, ..., ID_100]
                      |
                      v
               [asyncio.gather]
                      |
    +-----------------+-----------------+
    |        asyncio.Semaphore(10)      |
    |  [Slot 1]  [Slot 2] ... [Slot 10] |  <-- Máximo de 10 chamadas ativas na rede
    +-----------------+-----------------+
                      |
    (Tarefas 11 a 100 aguardam na fila FIFO)
                      |
                      v
          [Rede / JSONPlaceholder]

```

### 2.1 Mecanismo Matemático e Operacional do Semáforo

O semáforo assíncrono gerencia um contador atômico interno inicializado com `value = max_concurrency` (padrão: 10).

* **Entrada (`async with self._semaphore`):**
* Se `value > 0`, decrementa o contador em 1 (`value -= 1`) e permite que a corrotina prossiga imediatamente.
* Se `value == 0`, a corrotina suspende sua execução e ingressa em uma fila interna `collections.deque` de tarefas em espera, cedendo a CPU.


* **Saída (Ao finalizar o bloco de contexto):**
* Incrementa o contador (`value += 1`) e desperta imediatamente a próxima corrotina da fila FIFO.



### 2.2 Vetores de Falha Mitigados pelo Semáforo

1. **Socket Exhaustion & File Descriptor Exhaustion (OS Limit):** Cada socket aberto consome um descritor de arquivos no sistema operacional (limite `ulimit -n` no Linux). Disparar 10.000 requisições simultâneas causaria `OSError: [Errno 24] Too many open files`. O semáforo limita os descritores ativos a uma fração segura da capacidade do sistema.
2. **Proteção contra Banimento por Rate Limit Remoto:** APIs públicas e serviços de nuvem possuem firewalls de aplicação (WAF) que bloqueiam rajadas abruptas (*bursts*) de tráfego oriundas de um mesmo endereço IP com erros `HTTP 429 Too Many Requests` ou bloqueio de firewall `HTTP 403 Forbidden`. O semáforo suaviza a curva de tráfego, transformando um ataque em potencial em um fluxo ordenado de requisições.

---

## 3. Resiliência Adaptativa e Tratamento Especializado de HTTP 429

A comunicação com APIs remotas é inerentemente instável. O sistema implementa uma política de retry sofisticada e adaptativa em `backend/app/providers/external_user_provider.py` utilizando a biblioteca `tenacity`.

### 3.1 Classificação Estrita de Exceções: Falhas Transitórias vs. Falhas Fatais

Um erro comum em implementações amadoras de retry é retentar requisições cegamente diante de qualquer erro. O sistema diferencia com precisão matemática o que deve e o que **não deve** ser retentado:

```text
                             [Falha na Chamada HTTP]
                                        |
                   +--------------------+--------------------+
                   |                                         |
          [Falha Permanente]                        [Falha Transitória]
       (Ex.: HTTP 404 Not Found)              (Ex.: HTTP 429, 500, 503, Timeout)
                   |                                         |
                   v                                         v
         Levanta UserNotFoundError               Aplica Política de Retentativas
       SEM RETENTATIVA (Zero Wait)            (Tenacity Backoff com Jitter / Retry-After)

```

* **Falha Permanente (`UserNotFoundError`):**
* Quando a API remota retorna `HTTP 404 Not Found`, significa que o recurso não existe na base de dados.
* **Decisão:** Retentar um 404 é um desperdício de tempo e recursos de rede. A exceção `UserNotFoundError` é levantada imediatamente e excluída expressamente da tupla de retentativas do Tenacity (`retry_if_exception_type`).


* **Falhas Transitórias (`ProviderServerError`, `ProviderTimeoutError`, `ProviderRateLimitError`):**
* Instabilidades temporárias de roteamento, timeouts de socket e sobrecargas transitórias de servidores de terceiros.
* **Decisão:** Retentar até 3 vezes (`stop_after_attempt(3)`).



### 3.2 Estratégia Customizada `wait_retry_after_or_exponential`

Quando um servidor remoto é sobrecarregado, ele emite o código `HTTP 429 Too Many Requests` e frequentemente inclui o cabeçalho padronizado `Retry-After`, que informa em quantos segundos o cliente deve aguardar antes de tentar novamente. Ignorar esse cabeçalho e continuar disparando retentativas viola o protocolo de cooperação da web e pode gerar banimento definitivo do IP.

O sistema implementa a classe `wait_retry_after_or_exponential` herdando de `tenacity.wait.wait_base`:

```python
# Referência: backend/app/providers/external_user_provider.py
class wait_retry_after_or_exponential(wait_base):
    def __init__(self, fallback_wait: wait_base, max_wait: float = 10.0):
        self.fallback_wait = fallback_wait
        self.max_wait = max_wait

    def __call__(self, retry_state: RetryCallState) -> float:
        if retry_state.outcome and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            # Se a falha foi por Rate Limit (HTTP 429) e veio com o cabeçalho Retry-After:
            if isinstance(exc, ProviderRateLimitError) and exc.retry_after is not None:
                # Respeita o cabeçalho do servidor remoto, limitado a um teto de segurança
                wait_time = min(float(exc.retry_after), self.max_wait)
                logger.info(
                    "tenacity_respecting_retry_after_header",
                    user_id=exc.user_id,
                    wait_seconds=wait_time,
                )
                return wait_time
        # Caso contrário, aplica o backoff exponencial com jitter padrão
        return self.fallback_wait(retry_state)

```

### 3.3 Recuo Exponencial com Jitter (Randomized Exponential Backoff)

Para falhas onde o cabeçalho `Retry-After` não é fornecido, a estratégia de fallback utiliza `wait_random_exponential(multiplier=0.5, max=2.0)`.

**Por que o Jitter Aleatório é Essencial?**
Se 20 requisições simultâneas falharem ao mesmo tempo (ex.: o servidor remoto caiu momentaneamente) e todas aplicarem um recuo exponencial fixo (ex.: exatamente 1s, depois 2s), todas as 20 requisições dispararão uma nova onda de choque simultânea contra o servidor exatamente no mesmo instante (*efeito de manada* ou *thundering herd problem*).
O **Jitter** adiciona um ruído pseudoaleatório à equação de espera:


$$WaitTime = \min(MaxWait, Uniform(0, Multiplier \times 2^{attempt}))$$


Isso distribui uniformemente as retentativas no eixo temporal, permitindo que o servidor remoto se recupere sem ser bombardeado por picos síncronos de tráfego.

```

```