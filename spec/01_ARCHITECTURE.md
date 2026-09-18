# 01. ARQUITETURA GERAL DO SISTEMA (CLEAN ARCHITECTURE & DDD)

## 1. Visão Sistêmica e Objetivos de Engenharia

O **Hit Digital - Async User Batch Fetcher** é uma solução corporativa full-stack projetada para ingestão concorrente, enriquecimento e consolidação resiliente de dados de usuários distribuídos. O sistema foi concebido para atender a três requisitos não funcionais críticos:

1. **Latência Mínima e Throughput Máximo:** Utilização do modelo assíncrono não-bloqueante baseado em corrotinas do Python (`asyncio`) para eliminar esperas ociosas de rede.
2. **Isolamento Absoluto de Falhas (Bulkhead Pattern):** Garantir que falhas parciais em IDs individuais (ex.: timeouts, HTTP 404, HTTP 429) não causem a rejeição total do lote de dados.
3. **Desacoplamento Arquitetural Estrito (Clean Architecture & DIP):** Proteção do núcleo de regras de negócio contra detalhes de infraestrutura (provedores HTTP externos, drivers de banco de dados e frameworks web).

---

## 2. Diagrama de Fluxo de Dados e Topologia de Componentes

### 2.1 Diagrama Conceitual (Mermaid)

```mermaid
flowchart TD
    subgraph Frontend [Camada de Apresentação (React + TypeScript)]
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

    subgraph ServiceLayer [Camada de Aplicação & Orquestração]
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

    subgraph ExternalServices [Sistemas Externos & Persistência]
        JSONPlaceholder[(API Externa Remota: JSONPlaceholder)]
        DB[(Auditoria Assíncrona: SQLite / PostgreSQL)]
        Retry -->|HTTP GET /users/:id| JSONPlaceholder
        Service -.->|async record_batch_query| DB
    end

```

### 2.2 Fluxo Sequencial de Execução (ASCII Data Flow)

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
        |       |-- CACHE MISS: [2, 999] -> Prepara tarefas assíncronas
        v
[asyncio.Semaphore(10)]
        |-- 4. Dispara corrotinas isoladas via asyncio.gather(return_exceptions=True)
        |-- 5. Tarefa ID=2: Adquire slot -> HTTP GET /users/2 -> 200 OK -> Salva no Cache L1
        |-- 6. Tarefa ID=999: Adquire slot -> HTTP GET /users/999 -> 404 Not Found -> UserNotFoundError
        v
[Agregador do Serviço]
        |-- 7. Consolida: users=[UserResponse(1), UserResponse(2)], failed=[999], errors=[...]
        |-- 8. Dispara auditoria assíncrona no DB (fire-and-forget/non-blocking)
        v
[FastAPI Response]
        |-- 9. Retorna HTTP 200 OK com UserBatchResponse
        v
[Frontend React State]
        |-- 10. Atualiza tabelas de Sucesso, Falhas e Métricas de Auditoria

```

---

## 3. Arquitetura de Camadas (Clean Architecture & DDD)

O backend adota os princípios da **Clean Architecture** formulados por Robert C. Martin e preceitos táticos do **Domain-Driven Design (DDD)**. As dependências fluem exclusivamente de fora para dentro: a camada de domínio desconhece a existência do framework FastAPI, da biblioteca HTTPX ou do banco SQLAlchemy.

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

A entidade `User` representa o conceito puro de negócio de um usuário no sistema. Ela é modelada utilizando `@dataclass(frozen=True)` da biblioteca padrão do Python, garantindo:

* **Imutabilidade Estrutural:** Previne efeitos colaterais acidentais entre corrotinas que manipulam o mesmo objeto em memória.
* **Zero Dependências Externas:** Não herda de `pydantic.BaseModel` nem de `sqlalchemy.orm.DeclarativeBase`, permanecendo imune a quebras causadas por atualizações de bibliotecas de terceiros.
* **Comportamento Rico de Domínio:** Expõe propriedades e métodos calculados (ex.: `display_identifier`) em vez de ser um mero modelo anêmico.

```python
# Referência: backend/app/domain/models/user.py
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

### 3.2 Provider Layer e Princípio de Inversão de Dependência (`backend/app/providers/`)

Para cumprir o **Dependency Inversion Principle (DIP)** (letra 'D' do SOLID), o serviço de aplicação não consome diretamente a classe concreta `ExternalUserProvider`. Em vez disso, estabelece um contrato abstrato formal:

1. **Interface Abstrata (`backend/app/providers/base.py`):**
A classe `BaseUserProvider(ABC)` declara o contrato assíncrono `fetch_user_by_id(user_id: int) -> Dict[str, Any]`. Ela define as exceções esperadas no contrato de domínio (`UserNotFoundError`, `ProviderError`).
2. **Implementação Concreta (`backend/app/providers/external_user_provider.py`):**
Encapsula os detalhes de protocolo HTTP, cabeçalhos, manipulação de erros com `httpx.AsyncClient` e resiliência com a biblioteca `tenacity`.
3. **Benefícios Arquiteturais:**
* **Testabilidade Determinística:** Em suítes de teste de integração e unidade (`backend/tests/`), o provedor pode ser substituído por um `MockUserProvider` sem necessidade de abrir sockets de rede ou interceptar chamadas via monkey-patching frágil.
* **Pluggability:** Se a fonte de dados for migrada da API pública do JSONPlaceholder para uma API interna da Hit Digital, para o Auth0 ou para um diretório LDAP/Active Directory, nenhuma linha do `UserFetchService` precisa ser alterada.



### 3.3 Service Layer (`backend/app/services/user_fetch_service.py`)

O `UserFetchService` atua como o maestro do caso de uso de consulta em lote. Ele é responsável por:

1. **Governança de Concorrência:** Instancia e gerencia o `asyncio.Semaphore`, assegurando que o número de requisições simultâneas permaneça estritamente contido no teto configurado (`MAX_CONCURRENCY`).
2. **Ciclo de Consulta ao Cache L1:** Intercepta as chamadas para consultar o cache antes de emitir tráfego para a rede, registrando se o resultado foi um `cache_hit`.
3. **Agregação e Isolamento:** Itera sobre a tupla de resultados de `asyncio.gather(return_exceptions=True)`, categorizando cada item em `users` (sucessos) ou `failed`/`errors` (falhas granulares).
4. **Auditoria Assíncrona Não-Bloqueante:** Dispara a gravação dos metadados da consulta no banco de dados através da função `record_batch_query`, sem bloquear o retorno HTTP ao cliente.

### 3.4 API & Presentation Layer (`backend/app/api/`)

A camada de apresentação é implementada com **FastAPI** e **Pydantic V2**:

* **Injeção de Dependências (`backend/app/api/v1/endpoints/users.py`):** Utiliza `Depends` para injetar instâncias compartilhadas do pool de conexões HTTP, configurações centralizadas (`Settings`) e cache.
* **Roteamento Duplo e Versionamento:** Expõe simultaneamente os endpoints `/api/users/fetch` (estrita aderência à especificação do desafio técnico) e `/api/v1/users/fetch` (boas práticas de versionamento semântico de APIs corporativas).

---

## 4. Ciclo de Vida da Aplicação (`lifespan`) e Gestão de Conexões HTTP

Em aplicações assíncronas de alta performance, a instanciação ingênua de clientes HTTP a cada requisição (`async with httpx.AsyncClient() as client:`) é um anti-padrão grave que acarreta:

1. **Sobrecarga de Handshake TLS/TCP:** O custo computacional e de latência de estabelecer um novo handshake TLS a cada ID consultado.
2. **Esgotamento de Portas Locais (Socket Exhaustion / TIME_WAIT):** O fechamento prematuro de sockets deixa portas no estado `TIME_WAIT` do kernel do sistema operacional, exaurindo portas efêmeras.
3. **Falhas Intermitentes de Desconexão Unilateral (`httpcore.RemoteProtocolError`):** Servidores remotos frequentemente derrubam conexões ociosas mantidas por clientes mal-configurados.

### 4.1 Configuração Avançada do Connection Pool (`backend/app/main.py`)

Para solucionar integralmente esses vetores de falha, o backend implementa o gerenciador de contexto assíncrono `lifespan`:

```python
# Referência: backend/app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("application_startup", project=settings.PROJECT_NAME, version=settings.VERSION)

    # 1. Configuração Estrita de Limites e Conexões
    limits = httpx.Limits(
        max_keepalive_connections=10,  # Máximo de conexões ociosas mantidas ativas
        max_connections=20,            # Teto rígido de conexões concorrentes no pool
        keepalive_expiry=5.0,          # Conexões ociosas expiram antes do encerramento pelo servidor
    )

    # 2. Timeouts Granulares por Fase do Ciclo HTTP
    timeout = httpx.Timeout(
        connect=3.0,  # Tempo máximo para estabelecer o socket TCP + Handshake TLS
        read=7.0,     # Tempo máximo de espera pela resposta do servidor remoto
        write=5.0,    # Tempo máximo para transmissão do payload de requisição
        pool=5.0,     # Tempo máximo de espera para obter uma conexão livre do pool
    )

    client = httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=True,
    )
    app.state.http_client = client

    # 3. Inicialização Resiliente do Banco de Dados
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

### 4.2 Mitigação da Falha `httpcore.RemoteProtocolError`

A falha clássica `httpcore.RemoteProtocolError: Server disconnected without sending a response` ocorre quando o cliente tenta reutilizar uma conexão HTTP do pool Keep-Alive no exato milissegundo em que o servidor remoto (JSONPlaceholder/Cloudflare) já a encerrou por inatividade (*idle timeout*).

**Mecanismo de Mitigação Implementado:**

* Definindo `keepalive_expiry=5.0` segundos, o `httpx.AsyncClient` do Hit Digital descarta e renova preventivamente conexões que permaneceram ociosas por 5 segundos. Como os balanceadores de carga remotos costumam ter keep-alive timeout de 15 a 60 segundos, o cliente encerra a conexão antes que o servidor o faça, eliminando a corrida de encerramento unilateral.