# 01. ARQUITETURA GERAL DO SISTEMA (CLEAN ARCHITECTURE & DDD)

## 1. Vis?o Sist?mica e Objetivos de Engenharia

O **Hit Digital - Async User Batch Fetcher** ? uma solu??o corporativa full-stack projetada para ingest?o concorrente, enriquecimento e consolida??o resiliente de dados de usu?rios distribu?dos. O sistema foi concebido para atender a tr?s requisitos n?o funcionais cr?ticos:
1. **Lat?ncia M?nima e Throughput M?ximo:** Utiliza??o do modelo ass?ncrono n?o-bloqueante baseado em corrotinas do Python (`asyncio`) para eliminar esperas ociosas de rede.
2. **Isolamento Absoluto de Falhas (Bulkhead Pattern):** Garantir que falhas parciais em IDs individuais (ex.: timeouts, HTTP 404, HTTP 429) n?o causem a rejei??o total do lote de dados.
3. **Desacoplamento Arquitetural Estrito (Clean Architecture & DIP):** Prote??o do n?cleo de regras de neg?cio contra detalhes de infraestrutura (provedores HTTP externos, drivers de banco de dados e frameworks web).

---

## 2. Diagrama de Fluxo de Dados e Topologia de Componentes

### 2.1 Diagrama Conceitual (Mermaid)

```mermaid
flowchart TD
    subgraph Frontend [Camada de Apresenta??o (React + TypeScript)]
        UI[Console SPA: UserBatchForm & UserResultsTable]
        Hook[Custom Hook: useFetchUsers]
        APIClient[HTTP Client: apiClient / Fetch API]
        UI --> Hook --> APIClient
    end

    subgraph Gateway [API Gateway & Routing Layer (FastAPI)]
        Router[Router: /api/users/fetch & /api/v1/users/fetch]
        Validator[Pydantic V2 Validation: UserFetchRequest]
        Lifespan[Lifespan Context: HTTP Pool & DB Engine]
        APIClient -->|POST /api/users/fetch| Router
        Router --> Validator
        Lifespan -.-> Router
    end

    subgraph ServiceLayer [Camada de Aplica??o & Orquestra??o]
        Service[UserFetchService]
        Semaphore[asyncio.Semaphore: max_concurrency=10]
        Gather[asyncio.gather: return_exceptions=True]
        L1Cache[(InMemoryTTLCache: TTL 60s)]
        Validator --> Service
        Service --> Semaphore
        Service --> Gather
        Service <-->|Get / Set| L1Cache
    end

    subgraph ProviderLayer [Camada de Provedor Externo (DIP)]
        Interface[<<interface>> BaseUserProvider]
        Impl[ExternalUserProvider: httpx.AsyncClient]
        Retry[Tenacity Engine: wait_retry_after_or_exponential]
        Interface <|.. Impl
        Gather --> Interface
        Impl --> Retry
    end

    subgraph ExternalServices [Sistemas Externos & Persist?ncia]
        JSONPlaceholder[(API Externa Remota: JSONPlaceholder)]
        DB[(Auditoria Ass?ncrona: SQLite / PostgreSQL)]
        Retry -->|HTTP GET /users/:id| JSONPlaceholder
        Service -.->|async record_batch_query| DB
    end
```

### 2.2 Fluxo Sequencial de Execu??o (ASCII Data Flow)

```text
[Cliente HTTP / Frontend]
        |
        | 1. POST /api/users/fetch {"user_ids": [1, 2, 2, 999]}
        v
[FastAPI / Pydantic V2]
        | 2. Valida > 0, <= 100 itens, deduplica -> [1, 2, 999]
        v
[UserFetchService]
        |-- 3. Verifica Cache L1 (user:1, user:2, user:999)
        |       |-- CACHE HIT: user:1 -> Retorna imediatamente
        |       |-- CACHE MISS: [2, 999] -> Prepara tarefas ass?ncronas
        v
[asyncio.Semaphore(10)]
        |-- 4. Dispara corrotinas isoladas via asyncio.gather(return_exceptions=True)
        |-- 5. Tarefa ID=2: Adquire slot -> HTTP GET /users/2 -> 200 OK -> Salva no Cache L1
        |-- 6. Tarefa ID=999: Adquire slot -> HTTP GET /users/999 -> 404 Not Found -> UserNotFoundError
        v
[Agregador do Servi?o]
        |-- 7. Consolida: users=[UserResponse(1), UserResponse(2)], failed=[999], errors=[...]
        |-- 8. Dispara auditoria ass?ncrona no DB (fire-and-forget/non-blocking)
        v
[FastAPI Response]
        |-- 9. Retorna HTTP 200 OK com UserBatchResponse
        v
[Frontend React State]
        |-- 10. Atualiza tabelas de Sucesso, Falhas e M?tricas de Auditoria
```

---

## 3. Arquitetura de Camadas (Clean Architecture & DDD)

O backend adota os princ?pios da **Clean Architecture** formulados por Robert C. Martin e preceitos t?ticos do **Domain-Driven Design (DDD)**. As depend?ncias fluem exclusivamente de fora para dentro: a camada de dom?nio desconhece a exist?ncia do framework FastAPI, da biblioteca HTTPX ou do banco SQLAlchemy.

```text
+-------------------------------------------------------------+
| 1. API / Presentation Layer (FastAPI Routes, Schemas, CORS) |
|   +---------------------------------------------------------+
|   | 2. Service Layer (UserFetchService, Batch Orchestration)|
|   |   +-----------------------------------------------------+
|   |   | 3. Provider Layer (BaseUserProvider, Retry Policy)  |
|   |   |   +-------------------------------------------------+
|   |   |   | 4. Domain Layer (User Entity, Core Business)    |
+---+---+---+---+---------------------------------------------+
```

### 3.1 Domain Layer (`backend/app/domain/models/user.py`)
A entidade `User` representa o conceito puro de neg?cio de um usu?rio no sistema. Ela ? modelada utilizando `@dataclass(frozen=True)` da biblioteca padr?o do Python, garantindo:
- **Imutabilidade Estrutural:** Previne efeitos colaterais acidentais entre corrotinas que manipulam o mesmo objeto em mem?ria.
- **Zero Depend?ncias Externas:** N?o herda de `pydantic.BaseModel` nem de `sqlalchemy.orm.DeclarativeBase`, permanecendo imune a quebras causadas por atualiza??es de bibliotecas de terceiros.
- **Comportamento Rico de Dom?nio:** Exp?e propriedades e m?todos calculados (ex.: `display_identifier`) em vez de ser um mero modelo an?mico.

```python
# Refer?ncia: backend/app/domain/models/user.py
@dataclass(frozen=True)
class User:
    id: int
    name: str
    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    company_name: Optional[str] = None

    @property
    def display_identifier(self) -> str:
        return f"{self.name} (@{self.username})" if self.username else self.name
```

### 3.2 Provider Layer e Princ?pio de Invers?o de Depend?ncia (`backend/app/providers/`)
Para cumprir o **Dependency Inversion Principle (DIP)** (letra 'D' do SOLID), o servi?o de aplica??o n?o consome diretamente a classe concreta `ExternalUserProvider`. Em vez disso, estabelece um contrato abstrato formal:

1. **Interface Abstrata (`backend/app/providers/base.py`):**
   A classe `BaseUserProvider(ABC)` declara o contrato ass?ncrono `fetch_user_by_id(user_id: int) -> Dict[str, Any]`. Ela define as exce??es esperadas no contrato de dom?nio (`UserNotFoundError`, `ProviderError`).
2. **Implementa??o Concreta (`backend/app/providers/external_user_provider.py`):**
   Encapsula os detalhes de protocolo HTTP, cabe?alhos, manipula??o de erros com `httpx.AsyncClient` e resili?ncia com a biblioteca `tenacity`.
3. **Benef?cios Arquiteturais:**
   - **Testabilidade Determin?stica:** Em su?tes de teste de integra??o e unidade (`backend/tests/`), o provedor pode ser substitu?do por um `MockUserProvider` sem necessidade de abrir sockets de rede ou interceptar chamadas via monkey-patching fr?gil.
   - **Pluggability:** Se a fonte de dados for migrada da API p?blica do JSONPlaceholder para uma API interna da Hit Digital, para o Auth0 ou para um diret?rio LDAP/Active Directory, nenhuma linha do `UserFetchService` precisa ser alterada.

### 3.3 Service Layer (`backend/app/services/user_fetch_service.py`)
O `UserFetchService` atua como o maestro do caso de uso de consulta em lote. Ele ? respons?vel por:
1. **Governan?a de Concorr?ncia:** Instancia e gerencia o `asyncio.Semaphore`, assegurando que o n?mero de requisi??es simult?neas permane?a estritamente contido no teto configurado (`MAX_CONCURRENCY`).
2. **Ciclo de Consulta ao Cache L1:** Intercepta as chamadas para consultar o cache antes de emitir tr?fego para a rede, registrando se o resultado foi um `cache_hit`.
3. **Agrega??o e Isolamento:** Itera sobre a tupla de resultados de `asyncio.gather(return_exceptions=True)`, categorizando cada item em `users` (sucessos) ou `failed`/`errors` (falhas granulares).
4. **Auditoria Ass?ncrona N?o-Bloqueante:** Dispara a grava??o dos metadados da consulta no banco de dados atrav?s da fun??o `record_batch_query`, sem bloquear o retorno HTTP ao cliente.

### 3.4 API & Presentation Layer (`backend/app/api/`)
A camada de apresenta??o ? implementada com **FastAPI** e **Pydantic V2**:
- **Inje??o de Depend?ncias (`backend/app/api/v1/endpoints/users.py`):** Utiliza `Depends` para injetar inst?ncias compartilhadas do pool de conex?es HTTP, configura??es centralizadas (`Settings`) e cache.
- **Roteamento Duplo e Versionamento:** Exp?e simultaneamente os endpoints `/api/users/fetch` (estrita ader?ncia ? especifica??o do desafio t?cnico) e `/api/v1/users/fetch` (boas pr?ticas de versionamento sem?ntico de APIs corporativas).

---

## 4. Ciclo de Vida da Aplica??o (`lifespan`) e Gest?o de Conex?es HTTP

Em aplica??es ass?ncronas de alta performance, a instancia??o ing?nua de clientes HTTP a cada requisi??o (`async with httpx.AsyncClient() as client:`) ? um anti-padr?o grave que acarreta:
1. **Sobrecarga de Handshake TLS/TCP:** O custo computacional e de lat?ncia de estabelecer um novo handshake TLS a cada ID consultado.
2. **Esgotamento de Portas Locais (Socket Exhaustion / TIME_WAIT):** O fechamento prematuro de sockets deixa portas no estado `TIME_WAIT` do kernel do sistema operacional, exaurindo portas ef?meras.
3. **Falhas Intermitentes de Desconex?o Unilateral (`httpcore.RemoteProtocolError`):** Servidores remotos frequentemente derrubam conex?es ociosas mantidas por clientes mal-configurados.

### 4.1 Configura??o Avan?ada do Connection Pool (`backend/app/main.py`)
Para solucionar integralmente esses vetores de falha, o backend implementa o gerenciador de contexto ass?ncrono `lifespan`:

```python
# Refer?ncia: backend/app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("application_startup", project=settings.PROJECT_NAME, version=settings.VERSION)

    # 1. Configura??o Estrita de Limites e Conex?es
    limits = httpx.Limits(
        max_keepalive_connections=10,  # M?ximo de conex?es ociosas mantidas ativas
        max_connections=20,            # Teto r?gido de conex?es concorrentes no pool
        keepalive_expiry=5.0,          # Conex?es ociosas expiram antes do encerramento pelo servidor
    )

    # 2. Timeouts Granulares por Fase do Ciclo HTTP
    timeout = httpx.Timeout(
        connect=3.0,  # Tempo m?ximo para estabelecer o socket TCP + Handshake TLS
        read=7.0,     # Tempo m?ximo de espera pela resposta do servidor remoto
        write=5.0,    # Tempo m?ximo para transmiss?o do payload de requisi??o
        pool=5.0,     # Tempo m?ximo de espera para obter uma conex?o livre do pool
    )

    client = httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=True,
    )
    app.state.http_client = client

    # 3. Inicializa??o Resiliente do Banco de Dados
    try:
        await init_db()
    except Exception as db_exc:
        logger.warning("init_db_error_ignored_for_serverless", error=str(db_exc))

    yield

    # 4. Graceful Shutdown
    logger.info("application_shutdown_closing_http_pool")
    try:
        await client.aclose()
    except Exception:
        pass
    logger.info("application_shutdown_completed")
```

### 4.2 Mitiga??o da Falha `httpcore.RemoteProtocolError`
A falha cl?ssica `httpcore.RemoteProtocolError: Server disconnected without sending a response` ocorre quando o cliente tenta reutilizar uma conex?o HTTP do pool Keep-Alive no exato milissegundo em que o servidor remoto (JSONPlaceholder/Cloudflare) j? a encerrou por inatividade (*idle timeout*).

**Mecanismo de Mitiga??o Implementado:**
- Definindo `keepalive_expiry=5.0` segundos, o `httpx.AsyncClient` do Hit Digital descarta e renova preventivamente conex?es que permaneceram ociosas por 5 segundos. Como os balanceadores de carga remotos costumam ter keep-alive timeout de 15 a 60 segundos, o cliente encerra a conex?o antes que o servidor o fa?a, eliminando a corrida de encerramento unilateral.
