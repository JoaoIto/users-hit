# 02. ARCHITECTURAL DECISION RECORDS (ADR)

Este documento registra as decis?es arquiteturais estruturantes adotadas no desenvolvimento do **Hit Digital - Async User Batch Fetcher**, documentando o contexto de engenharia, a decis?o tomada, as justificativas t?cnicas, consequ?ncias positivas e os trade-offs admitidos.

---

## ADR-001: Padr?o Provider Abstrato vs. Chamadas HTTP Diretas

### Status
Aprovado e Implementado

### Contexto
O requisito fundamental do sistema ? consultar dados de usu?rios em uma API externa (inicialmente o JSONPlaceholder). Uma implementa??o ing?nua realizaria chamadas `httpx.get()` diretamente no interior do servi?o de orquestra??o (`UserFetchService`) ou nos controladores de rota do FastAPI. No entanto, o acoplamento direto a clientes HTTP ou endpoints espec?ficos viola o princ?pio Open/Closed (OCP) e o Dependency Inversion Principle (DIP), inviabilizando testes unit?rios sem mocks globais de rede e tornando a migra??o para outros provedores custosa e arriscada.

### Decis?o
Criar uma camada formal de abstra??o baseada em Classes Abstratas do Python (`abc.ABC`):
1. Definir o contrato `BaseUserProvider` em `backend/app/providers/base.py`, expondo o m?todo abstrato `fetch_user_by_id(user_id: int) -> Dict[str, Any]`.
2. Implementar `ExternalUserProvider` em `backend/app/providers/external_user_provider.py` como implementa??o concreta, injetando o cliente `httpx.AsyncClient`.
3. Injetar a abstra??o no `UserFetchService` via construtor (`dependency injection`).

### Consequ?ncias Positivas
- **Desacoplamento de Infraestrutura:** O servi?o de dom?nio n?o sabe como a rede ? acessada, nem quais bibliotecas (HTTPX, AIOHTTP, Requests) s?o utilizadas.
- **Testes Determin?sticos e Ultrarr?pidos:** Os testes unit?rios (`backend/tests/unit/test_service.py`) utilizam um `MockUserProvider` em mem?ria, executando dezenas de cen?rios de teste em milissegundos sem tr?fego de rede e sem risco de *flaky tests*.
- **Substitui??o Transparente de Provedores:** Qualquer migra??o futura para APIs internas da Hit Digital, bancos de dados legados ou servi?os gRPC exige apenas a escrita de uma nova classe derivada de `BaseUserProvider`, sem tocar nas regras de neg?cio.

### Trade-offs & Mitiga??es
- *Trade-off:* Pequeno overhead de indire??o de classes e chamadas polim?rficas em Python.
- *Mitiga??o:* O overhead de despacho de m?todos em Python (~50 nanosegundos) ? ordens de grandeza inferior ? lat?ncia de rede (~20 a 100 milissegundos), tornando o impacto computacional nulo.

---

## ADR-002: Isolamento de Falhas com `asyncio.gather(return_exceptions=True)`

### Status
Aprovado e Implementado

### Contexto
Ao processar lotes de at? 100 identificadores de usu?rios, ? imperativo lidar com heterogeneidade no status de cada recurso. Um lote pode conter IDs v?lidos (HTTP 200), IDs inexistentes (HTTP 404), servidores lentos com timeout ou falhas transit?rias de infraestrutura (HTTP 500/503). No padr?o tradicional de `asyncio.gather()`, o primeiro erro levantado aborta imediatamente todas as outras corrotinas do lote (*fail-fast*), descartando dados de IDs que foram ou seriam conclu?dos com sucesso.

### Decis?o
Adotar o padr?o **Bulkhead / Fault Isolation** atrav?s de `asyncio.gather(*tasks, return_exceptions=True)` em `backend/app/services/user_fetch_service.py`:
1. Cada ID ? processado em sua pr?pria corrotina isolada `_fetch_single_user(user_id)`.
2. A flag `return_exceptions=True` instrui o motor do `asyncio` a capturar quaisquer exce??es levantadas e inseri-las diretamente na lista de retornos, em vez de interromper o loop de eventos.
3. O agregador itera sobre o resultado consolidado e divide cirurgicamente os itens em:
   - `users`: Lista de objetos `UserResponse` enriquecidos e normalizados.
   - `failed`: Lista simples de inteiros `List[int]` com os IDs que falharam (estrita conformidade com o desafio).
   - `errors`: Lista de metadados granulares `List[FailedUserDetail]` especificando o c?digo HTTP e a causa t?cnica da falha de cada ID.

### Consequ?ncias Positivas
- **Maximiza??o da Taxa de Entrega de Dados:** Um usu?rio inexistente (404) ou um timeout isolado n?o prejudica os outros 99 usu?rios v?lidos do lote.
- **Observabilidade Granular:** O cliente recebe feedback detalhado do porqu? cada ID falhou, permitindo estrat?gias de reprocessamento seletivo.

### Trade-offs & Mitiga??es
- *Trade-off:* Complexidade acrescida no tratamento do retorno de `asyncio.gather`, exigindo checagem de tipos com `isinstance(result, Exception)` ou `isinstance(result, FailedUserDetail)`.
- *Mitiga??o:* Centraliza??o da l?gica de particionamento e mapeamento dentro de um ?nico m?todo testado exaustivamente (`_fetch_all_users`).

---

## ADR-003: Estrat?gia de Cache L1 com TTL vs. Cache Distribu?do

### Status
Aprovado e Implementado

### Contexto
O desafio exige um sistema eficiente para requisi??es repetidas aos mesmos IDs. Redes remotas imp?em lat?ncia de transfer?ncia e limita??es de cota (Rate Limits). Havia duas abordagens poss?veis:
1. Adotar Redis distribu?do como requisito mandat?rio da aplica??o.
2. Implementar um cache L1 local em mem?ria de processo com Time-To-Live (TTL) de 60 segundos, desacoplado por interface.

### Decis?o
Implementar a interface abstrata `BaseCache` (`backend/app/core/cache.py`) com a implementa??o concreta `InMemoryTTLCache`:
1. Armazenamento em dicion?rio Python thread-safe/async-safe associado a timestamps de expira??o (`monotonic()`).
2. Expira??o transparente sob demanda (lazy eviction) durante leituras (`get`), complementada por limpeza manual ou programada.
3. Configura??o de TTL padr?o de 60 segundos via `Settings.CACHE_TTL_SECONDS`.

### Consequ?ncias Positivas
- **Lat?ncia Sub-milissegundo:** Consultas com Cache Hit respondem em menos de 0.2ms, pois n?o h? serializa??o de rede para um cluster externo.
- **Zero Depend?ncias Obrigat?rias no Ambiente Local:** Permite que avaliadores e desenvolvedores executem o sistema imediatamente com `python run.py` sem necessitar de cont?ineres Docker ativos ou da porta 6379 aberta.
- **Flexibilidade Futura (DIP):** Como o `UserFetchService` depende apenas de `BaseCache`, a implementa??o de um `RedisCache` para clusters de m?ltiplos n?s requer apenas a cria??o de uma nova classe que respeite o contrato.

### Trade-offs & Mitiga??es
- *Trade-off:* Em ambientes serverless multi-inst?ncia (ex.: AWS Lambda / Vercel Functions), inst?ncias isoladas n?o compartilham a mesma mem?ria L1.
- *Mitiga??o:* Aceit?vel para o escopo de execu??o local e servidores dedicados (VPS/Render/Docker). O roadmap de escalabilidade documentado no `05_SCALABILITY_ROADMAP.md` especifica a topologia L1+L2 (Mem?ria + Redis) para ambientes distribu?dos massivos.

---

## ADR-004: Persist?ncia de Auditoria com SQLite Ass?ncrono

### Status
Aprovado e Implementado

### Contexto
O sistema precisa manter um registro hist?rico (auditoria) de cada lote consultado, contendo identificador da consulta (`query_id`), IDs solicitados, contagem de sucessos, falhas, cache hits e tempo de execu??o em milissegundos. 
O desafio principal reside em manter a compatibilidade tanto em desenvolvimento local (onde se deseja persistir em `./batch_history.db`) quanto em plataformas de nuvem serverless (como Vercel/AWS Lambda), onde o sistema de arquivos raiz (`/var/task`) ? estritamente **Read-Only**.

### Decis?o
1. Utilizar **SQLAlchemy 2.0 Ass?ncrono** com o driver `aiosqlite` (`sqlite+aiosqlite`).
2. Configurar a engine com `connect_args={"check_same_thread": False, "timeout": 30.0}` para suporte ass?ncrono seguro.
3. Implementar detec??o heur?stica e adaptativa de ambientes serverless e sistemas de arquivos somente leitura em `backend/app/core/database.py`:
   - Se `DATABASE_URL` estiver preenchida (ex.: PostgreSQL de produ??o), utiliza a URL configurada.
   - Caso contr?rio, detecta se o processo roda em ambiente serverless (`VERCEL`, `VERCEL_ENV`, `AWS_LAMBDA_FUNCTION_NAME`, `LAMBDA_TASK_ROOT` ou diret?rio local n?o grav?vel `not os.access(".", os.W_OK)`).
   - Se for serverless, redireciona o arquivo SQLite automaticamente para `/tmp/batch_history.db` (o ?nico diret?rio grav?vel na AWS Lambda/Vercel).
4. Gravar auditorias em background de forma n?o-bloqueante (`record_batch_query`), protegida por bloco de captura silenciosa de exce??es para garantir que uma indisponibilidade tempor?ria de disco nunca impe?a o cliente de receber os dados consultados.

### Consequ?ncias Positivas
- **Zero Configura??o Local:** Cria??o autom?tica da tabela `batch_queries` no startup sem necessidade de comandos adicionais de migra??o para rodar o projeto.
- **Imunidade a Read-Only Filesystem na Nuvem:** Elimina falhas de `sqlite3.OperationalError: unable to open database file` no deploy da Vercel.
- **Resili?ncia do Fluxo HTTP:** A grava??o da auditoria n?o compromete o SLA da resposta ao usu?rio.

### Trade-offs & Mitiga??es
- *Trade-off:* Em serverless, dados gravados em `/tmp` s?o descartados quando a inst?ncia da fun??o ? reciclada.
- *Mitiga??o:* Suporte nativo a PostgreSQL via vari?vel de ambiente `DATABASE_URL=postgresql://user:pass@host/db` para persist?ncia permanente em produ??o corporativa.

---

## ADR-005: Runner Unificado (`run.py`) vs. Gerenciadores de Processos Complexos

### Status
Aprovado e Implementado

### Contexto
Projetos full-stack compostos por backend Python (FastAPI/Uvicorn) e frontend Node.js (Vite/React) frequentemente imp?em fric??o de inicializa??o ao avaliador. A necessidade de abrir dois terminais manuais, instalar gerenciadores externos como `foreman`, `honcho`, `concurrently` ou for?ar o uso de cont?ineres `docker-compose` frequentemente resulta em erros de vers?o, portas presas ou falhas de terminal no Windows.

### Decis?o
Desenvolver um orquestrador unificado em Python puro na raiz do projeto (`run.py`):
1. **Valida??o Silenciosa de Pr?-requisitos:** Verifica a presen?a do Python (.venv priorit?rio) e npm, instalando depend?ncias faltantes automaticamente de forma transparente.
2. **Execu??o Concorrente Gerenciada:** Dispara o backend Uvicorn e o frontend Vite como sub-processos gerenciados (`subprocess.Popen`).
3. **Gerenciamento de Ciclo de Vida e Encerramento em ?rvore (Process Tree Kill):**
   - Registra manipuladores de `SIGINT` (Ctrl+C), `SIGTERM` e `atexit`.
   - No Windows, executa encerramento for?ado em ?rvore via `taskkill /F /T /PID <pid>`, garantindo a libera??o imediata das portas `8000` e `5173`.
   - No Linux/macOS, utiliza grupos de processo (`os.killpg(os.getpgid(pid), signal.SIGTERM)`).
4. **Interface Visual Profissional:** Exibe banner com codifica??o UTF-8 protegida contra falhas de p?gina de c?digo do terminal Windows (`cp1252`).

### Consequ?ncias Positivas
- **Experi?ncia de Avalia??o "One-Click":** O avaliador precisa apenas executar `python run.py`.
- **Preven??o de Portas Presas (Zombie Processes):** Nunca deixa processos ?rf?os ocupando a porta 8000 ou 5173 ap?s o encerramento do terminal.
- **Independ?ncia de Plataforma:** Funciona identicamente em Windows PowerShell, Command Prompt, macOS Terminal e distribui??es Linux.

### Trade-offs & Mitiga??es
- *Trade-off:* Manuten??o de c?digo em Python puro para gerenciamento de processos.
- *Mitiga??o:* O c?digo de `run.py` foi mantido autocontido, sem depend?ncias externas de terceiros, dependendo exclusivamente dos m?dulos da biblioteca padr?o (`subprocess`, `shutil`, `signal`, `atexit`, `os`, `sys`).
