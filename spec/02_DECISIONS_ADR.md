# 02. DECISION RECORDS (ADR)

Este documento registra as decisões arquiteturais estruturantes adotadas no desenvolvimento do **Hit Digital - Async User Batch Fetcher**, documentando o contexto de engenharia, a decisão tomada, as justificativas técnicas, consequências positivas e os trade-offs admitidos.

---

## ADR-001: Padrão Provider Abstrato vs. Chamadas HTTP Diretas

### Status

Aprovado e Implementado

### Contexto

O requisito fundamental do sistema é consultar dados de usuários em uma API externa (inicialmente o JSONPlaceholder). Uma implementação ingênua realizaria chamadas `httpx.get()` diretamente no interior do serviço de orquestração (`UserFetchService`) ou nos controladores de rota do FastAPI. No entanto, o acoplamento direto a clientes HTTP ou endpoints específicos viola o princípio Open/Closed (OCP) e o Dependency Inversion Principle (DIP), inviabilizando testes unitários sem mocks globais de rede e tornando a migração para outros provedores custosa e arriscada.

### Decisão

Criar uma camada formal de abstração baseada em Classes Abstratas do Python (`abc.ABC`):

1. Definir o contrato `BaseUserProvider` em `backend/app/providers/base.py`, expondo o método abstrato `fetch_user_by_id(user_id: int) -> Dict[str, Any]`.
2. Implementar `ExternalUserProvider` em `backend/app/providers/external_user_provider.py` como implementação concreta, injetando o cliente `httpx.AsyncClient`.
3. Injetar a abstração no `UserFetchService` via construtor (`dependency injection`).

### Consequências Positivas

* **Desacoplamento de Infraestrutura:** O serviço de domínio não sabe como a rede é acessada, nem quais bibliotecas (HTTPX, AIOHTTP, Requests) são utilizadas.
* **Testes Determinísticos e Ultrarrápidos:** Os testes unitários (`backend/tests/unit/test_service.py`) utilizam um `MockUserProvider` em memória, executando dezenas de cenários de teste em milissegundos sem tráfego de rede e sem risco de *flaky tests*.
* **Substituição Transparente de Provedores:** Qualquer migração futura para APIs internas da Hit Digital, bancos de dados legados ou serviços gRPC exige apenas a escrita de uma nova classe derivada de `BaseUserProvider`, sem tocar nas regras de negócio.

### Trade-offs & Mitigações

* *Trade-off:* Pequeno overhead de indireção de classes e chamadas polimórficas em Python.
* *Mitigação:* O overhead de despacho de métodos em Python (~50 nanosegundos) é ordens de grandeza inferior à latência de rede (~20 a 100 milissegundos), tornando o impacto computacional nulo.

---

## ADR-002: Isolamento de Falhas com `asyncio.gather(return_exceptions=True)`

### Status

Aprovado e Implementado

### Contexto

Ao processar lotes de até 100 identificadores de usuários, é imperativo lidar com heterogeneidade no status de cada recurso. Um lote pode conter IDs válidos (HTTP 200), IDs inexistentes (HTTP 404), servidores lentos com timeout ou falhas transitórias de infraestrutura (HTTP 500/503). No padrão tradicional de `asyncio.gather()`, o primeiro erro levantado aborta imediatamente todas as outras corrotinas do lote (*fail-fast*), descartando dados de IDs que foram ou seriam concluídos com sucesso.

### Decisão

Adotar o padrão **Bulkhead / Fault Isolation** através de `asyncio.gather(*tasks, return_exceptions=True)` em `backend/app/services/user_fetch_service.py`:

1. Cada ID é processado em sua própria corrotina isolada `_fetch_single_user(user_id)`.
2. A flag `return_exceptions=True` instrui o motor do `asyncio` a capturar quaisquer exceções levantadas e inseri-las diretamente na lista de retornos, em vez de interromper o loop de eventos.
3. O agregador itera sobre o resultado consolidado e divide cirurgicamente os itens em:
* `users`: Lista de objetos `UserResponse` enriquecidos e normalizados.
* `failed`: Lista simples de inteiros `List[int]` com os IDs que falharam (estrita conformidade com o desafio).
* `errors`: Lista de metadados granulares `List[FailedUserDetail]` especificando o código HTTP e a causa técnica da falha de cada ID.



### Consequências Positivas

* **Maximização da Taxa de Entrega de Dados:** Um usuário inexistente (404) ou um timeout isolado não prejudica os outros 99 usuários válidos do lote.
* **Observabilidade Granular:** O cliente recebe feedback detalhado do porquê cada ID falhou, permitindo estratégias de reprocessamento seletivo.

### Trade-offs & Mitigações

* *Trade-off:* Complexidade acrescida no tratamento do retorno de `asyncio.gather`, exigindo checagem de tipos com `isinstance(result, Exception)` ou `isinstance(result, FailedUserDetail)`.
* *Mitigação:* Centralização da lógica de particionamento e mapeamento dentro de um único método testado exaustivamente (`_fetch_all_users`).

---

## ADR-003: Estratégia de Cache L1 com TTL vs. Cache Distribuído

### Status

Aprovado e Implementado

### Contexto

O desafio exige um sistema eficiente para requisições repetidas aos mesmos IDs. Redes remotas impõem latência de transferência e limitações de cota (Rate Limits). Havia duas abordagens possíveis:

1. Adotar Redis distribuído como requisito mandatório da aplicação.
2. Implementar um cache L1 local em memória de processo com Time-To-Live (TTL) de 60 segundos, desacoplado por interface.

### Decisão

Implementar a interface abstrata `BaseCache` (`backend/app/core/cache.py`) com a implementação concreta `InMemoryTTLCache`:

1. Armazenamento em dicionário Python thread-safe/async-safe associado a timestamps de expiração (`monotonic()`).
2. Expiração transparente sob demanda (lazy eviction) durante leituras (`get`), complementada por limpeza manual ou programada.
3. Configuração de TTL padrão de 60 segundos via `Settings.CACHE_TTL_SECONDS`.

### Consequências Positivas

* **Latência Sub-milissegundo:** Consultas com Cache Hit respondem em menos de 0.2ms, pois não há serialização de rede para um cluster externo.
* **Zero Dependências Obrigatórias no Ambiente Local:** Permite que avaliadores e desenvolvedores executem o sistema imediatamente com `python run.py` sem necessitar de contêineres Docker ativos ou da porta 6379 aberta.
* **Flexibilidade Futura (DIP):** Como o `UserFetchService` depende apenas de `BaseCache`, a implementação de um `RedisCache` para clusters de múltiplos nós requer apenas a criação de uma nova classe que respeite o contrato.

### Trade-offs & Mitigações

* *Trade-off:* Em ambientes serverless multi-instância (ex.: AWS Lambda / Vercel Functions), instâncias isoladas não compartilham a mesma memória L1.
* *Mitigação:* Aceitável para o escopo de execução local e servidores dedicados (VPS/Render/Docker). O roadmap de escalabilidade documentado no `05_SCALABILITY_ROADMAP.md` especifica a topologia L1+L2 (Memória + Redis) para ambientes distribuídos massivos.

---

## ADR-004: Persistência de Auditoria com SQLite Assíncrono

### Status

Aprovado e Implementado

### Contexto

O sistema precisa manter um registro histórico (auditoria) de cada lote consultado, contendo identificador da consulta (`query_id`), IDs solicitados, contagem de sucessos, falhas, cache hits e tempo de execução em milissegundos.
O desafio principal reside em manter a compatibilidade tanto em desenvolvimento local (onde se deseja persistir em `./batch_history.db`) quanto em plataformas de nuvem serverless (como Vercel/AWS Lambda), onde o sistema de arquivos raiz (`/var/task`) é estritamente **Read-Only**.

### Decisão

1. Utilizar **SQLAlchemy 2.0 Assíncrono** com o driver `aiosqlite` (`sqlite+aiosqlite`).
2. Configurar a engine com `connect_args={"check_same_thread": False, "timeout": 30.0}` para suporte assíncrono seguro.
3. Implementar detecção heurística e adaptativa de ambientes serverless e sistemas de arquivos somente leitura em `backend/app/core/database.py`:
* Se `DATABASE_URL` estiver preenchida (ex.: PostgreSQL de produção), utiliza a URL configurada.
* Caso contrário, detecta se o processo roda em ambiente serverless (`VERCEL`, `VERCEL_ENV`, `AWS_LAMBDA_FUNCTION_NAME`, `LAMBDA_TASK_ROOT` ou diretório local não gravável `not os.access(".", os.W_OK)`).
* Se for serverless, redireciona o arquivo SQLite automaticamente para `/tmp/batch_history.db` (o único diretório gravável na AWS Lambda/Vercel).


4. Gravar auditorias em background de forma não-bloqueante (`record_batch_query`), protegida por bloco de captura silenciosa de exceções para garantir que uma indisponibilidade temporária de disco nunca impeça o cliente de receber os dados consultados.

### Consequências Positivas

* **Zero Configuração Local:** Criação automática da tabela `batch_queries` no startup sem necessidade de comandos adicionais de migração para rodar o projeto.
* **Imunidade a Read-Only Filesystem na Nuvem:** Elimina falhas de `sqlite3.OperationalError: unable to open database file` no deploy da Vercel.
* **Resiliência do Fluxo HTTP:** A gravação da auditoria não compromete o SLA da resposta ao usuário.

### Trade-offs & Mitigações

* *Trade-off:* Em serverless, dados gravados em `/tmp` são descartados quando a instância da função é reciclada.
* *Mitigação:* Suporte nativo a PostgreSQL via variável de ambiente `DATABASE_URL=postgresql://user:pass@host/db` para persistência permanente em produção corporativa.

---

## ADR-005: Runner Unificado (`run.py`) vs. Gerenciadores de Processos Complexos

### Status

Aprovado e Implementado

### Contexto

Projetos full-stack compostos por backend Python (FastAPI/Uvicorn) e frontend Node.js (Vite/React) frequentemente impõem fricção de inicialização ao avaliador. A necessidade de abrir dois terminais manuais, instalar gerenciadores externos como `foreman`, `honcho`, `concurrently` ou forçar o uso de contêineres `docker-compose` frequentemente resulta em erros de versão, portas presas ou falhas de terminal no Windows.

### Decisão

Desenvolver um orquestrador unificado em Python puro na raiz do projeto (`run.py`):

1. **Validação Silenciosa de Pré-requisitos:** Verifica a presença do Python (.venv prioritário) e npm, instalando dependências faltantes automaticamente de forma transparente.
2. **Execução Concorrente Gerenciada:** Dispara o backend Uvicorn e o frontend Vite como sub-processos gerenciados (`subprocess.Popen`).
3. **Gerenciamento de Ciclo de Vida e Encerramento em Árvore (Process Tree Kill):**
* Registra manipuladores de `SIGINT` (Ctrl+C), `SIGTERM` e `atexit`.
* No Windows, executa encerramento forçado em árvore via `taskkill /F /T /PID <pid>`, garantindo a liberação imediata das portas `8000` e `5173`.
* No Linux/macOS, utiliza grupos de processo (`os.killpg(os.getpgid(pid), signal.SIGTERM)`).


4. **Interface Visual Profissional:** Exibe banner com codificação UTF-8 protegida contra falhas de página de código do terminal Windows (`cp1252`).

### Consequências Positivas

* **Experiência de Avaliação "One-Click":** O avaliador precisa apenas executar `python run.py`.
* **Prevenção de Portas Presas (Zombie Processes):** Nunca deixa processos órfãos ocupando a porta 8000 ou 5173 após o encerramento do terminal.
* **Independência de Plataforma:** Funciona identicamente em Windows PowerShell, Command Prompt, macOS Terminal e distribuições Linux.

### Trade-offs & Mitigações

* *Trade-off:* Manutenção de código em Python puro para gerenciamento de processos.
* *Mitigação:* O código de `run.py` foi mantido autocontido, sem dependências externas de terceiros, dependendo exclusivamente dos módulos da biblioteca padrão (`subprocess`, `shutil`, `signal`, `atexit`, `os`, `sys`).