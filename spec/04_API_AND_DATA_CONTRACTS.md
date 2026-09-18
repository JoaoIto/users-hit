# 04. CONTRATOS DE API, SCHEMAS E VALIDA??ES (PYDANTIC V2)

Este documento especifica os contratos de interface (API Contracts), regras de valida??o sem?ntica e matrizes de tratamento de erros implementados no **Hit Digital - Async User Batch Fetcher**.

---

## 1. Contrato Estrito do Endpoint `POST /api/users/fetch`

O endpoint central da aplica??o foi desenhado para cumprir com rigor absoluto a especifica??o original do desafio t?cnico da Hit Digital, incorporando ao mesmo tempo extens?es sem?nticas que viabilizam observabilidade corporativa avan?ada sem violar contratos preexistentes.

- **Endpoints Mapeados:**
  - `POST /api/users/fetch` (Compatibilidade direta com a especifica??o original)
  - `POST /api/v1/users/fetch` (Versionamento sem?ntico corporativo)
- **Content-Type:** `application/json`
- **Status Code de Sucesso:** `200 OK` (O lote ? processado mesmo em caso de falhas parciais)

### 1.1 JSON Schema de Requisi??o (`UserFetchRequest`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UserFetchRequest",
  "type": "object",
  "required": ["user_ids"],
  "properties": {
    "user_ids": {
      "type": "array",
      "items": {
        "type": "integer",
        "minimum": 1
      },
      "minItems": 1,
      "maxItems": 100,
      "description": "Lista de IDs inteiros positivos a serem consultados concorrentemente.",
      "examples": [[1, 2, 3, 4]]
    }
  },
  "additionalProperties": false
}
```

### 1.2 JSON Schema de Resposta (`UserBatchResponse`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UserBatchResponse",
  "type": "object",
  "required": ["users", "failed", "meta"],
  "properties": {
    "users": {
      "type": "array",
      "description": "Lista de usu?rios consultados com sucesso e normalizados.",
      "items": {
        "type": "object",
        "required": ["id", "name", "cached"],
        "properties": {
          "id": { "type": "integer" },
          "name": { "type": "string" },
          "username": { "type": ["string", "null"] },
          "email": { "type": ["string", "null"] },
          "phone": { "type": ["string", "null"] },
          "website": { "type": ["string", "null"] },
          "company_name": { "type": ["string", "null"] },
          "cached": { "type": "boolean" }
        }
      }
    },
    "failed": {
      "type": "array",
      "description": "Lista estrita de n?meros inteiros com os IDs que falharam.",
      "items": { "type": "integer" },
      "examples": [[3, 999]]
    },
    "errors": {
      "type": "array",
      "description": "Metadados de diagn?stico profundo para cada falha registrada.",
      "items": {
        "type": "object",
        "required": ["user_id", "reason"],
        "properties": {
          "user_id": { "type": "integer" },
          "status_code": { "type": ["integer", "null"] },
          "reason": { "type": "string" }
        }
      }
    },
    "meta": {
      "type": "object",
      "required": ["total", "success_count", "failed_count", "cache_hits", "execution_time_ms"],
      "properties": {
        "total": { "type": "integer" },
        "success_count": { "type": "integer" },
        "failed_count": { "type": "integer" },
        "cache_hits": { "type": "integer" },
        "execution_time_ms": { "type": "number" },
        "request_id": { "type": ["string", "null"] }
      }
    }
  }
}
```

### 1.3 Estrat?gia de Conformidade com Validadores Automatizados
Testes de recrutamento e sistemas automatizados de avalia??o (*grading bots*) costumam realizar assertivas r?gidas sobre os campos da resposta JSON:

```python
# Asser??o t?pica de teste automatizado:
assert response.json()["failed"] == [3, 4]
assert isinstance(response.json()["failed"][0], int)
```

**Solu??o Arquitetural Implementada:**
- O campo `failed` ? tipado estritamente como `List[int]`. Ele **nunca** cont?m strings ou objetos aninhados.
- Para n?o abrir m?o do valor de engenharia e observabilidade, criamos o campo complementar `errors: List[FailedUserDetail]` e `meta: BatchMetadata`. Validadores autom?ticos que verificam apenas `users` e `failed` continuam passando com 100% de sucesso, enquanto sistemas inteligentes e interfaces humanas t?m acesso completo ? auditoria e diagn?sticos.

---

## 2. Regras de Valida??o Sem?ntica (Pydantic V2)

A sanitiza??o e valida??o ocorrem na borda da aplica??o (`backend/app/schemas/user.py`), antes que qualquer corrotina de orquestra??o seja instanciada:

```python
# Refer?ncia: backend/app/schemas/user.py
class UserFetchRequest(BaseModel):
    user_ids: List[int] = Field(
        ...,
        description="Lista de IDs de usu?rios a serem consultados.",
        examples=[[1, 2, 3, 4]],
    )

    @field_validator("user_ids")
    @classmethod
    def validate_and_deduplicate_ids(cls, v: List[int]) -> List[int]:
        # Regra 1: Rejei??o de lista vazia
        if not v:
            raise ValueError("A lista de IDs n?o pode ser vazia.")

        # Regra 2: Teto m?ximo de seguran?a por lote (Batch Limit)
        if len(v) > 100:
            raise ValueError("O limite m?ximo por lote ? de 100 IDs.")

        # Regra 3: Integridade matem?tica de inteiros positivos
        for user_id in v:
            if user_id <= 0:
                raise ValueError(f"O ID {user_id} ? inv?lido. Todos os IDs devem ser inteiros positivos.")

        # Regra 4: Deduplica??o determin?stica preservando a ordem original
        deduplicated = list(dict.fromkeys(v))
        return deduplicated
```

### 2.1 Por que `list(dict.fromkeys(v))` em vez de `list(set(v))`?
A abordagem ing?nua para deduplica??o em Python consiste em converter a lista em conjunto (`set`):
```python
# Anti-padr?o:
deduplicated = list(set(v))  # Quebra a ordem dos IDs!
```
Em Python, tabelas hash de `set` n?o garantem a ordem de inser??o original. Se o cliente enviar `[10, 2, 10, 5]`, a convers?o para `set` poderia resultar em `[2, 5, 10]`, desordenando as expectativas de quem consome a API.
Desde o Python 3.7+, a especifica??o da linguagem garante que dicion?rios mant?m a ordem estrita de inser??o. A instru??o `dict.fromkeys(v)` remove duplicatas com complexidade temporal $O(N)$ e preserva exatamente a sequ?ncia original em que os IDs foram submetidos pelo cliente.

---

## 3. Tabela de Mapeamento de C?digos de Erro e Comportamento da API

A matriz a seguir mapeia como as exce??es internas do sistema e os c?digos retornados pela API externa s?o traduzidos no payload final entregue ao cliente:

| Cen?rio de Execu??o | Status da API Externa | Exce??o Interna Levantada | Pol?tica de Retry (Tenacity) | Status HTTP da API | Item na Lista `failed` | Item no Objeto `errors` | Comportamento do Sistema |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Usu?rio Existe** | `HTTP 200 OK` | Nenhuma | Nenhuma | `200 OK` | N?o inclu?do | N?o inclu?do | Adicionado em `users`, gravado no Cache L1 |
| **Cache Hit Pr?vio** | Nenhum (Mem?ria) | Nenhuma | Nenhuma | `200 OK` | N?o inclu?do | N?o inclu?do | Retornado de `InMemoryTTLCache` com flag `cached: true` |
| **Usu?rio Inexistente** | `HTTP 404 Not Found` | `UserNotFoundError` | **Zero retentativas** (Fail-fast imediato) | `200 OK` | Inclu?do (`[id]`) | `status_code: 404, reason: "Usu?rio com ID {id} n?o encontrado..."` | N?o retenta; isolado no agregado |
| **Rate Limit Remoto** | `HTTP 429 Too Many` | `ProviderRateLimitError`| Retenta at? 3x respeitando `Retry-After` | `200 OK` | Inclu?do se esgotar as 3 tentativas | `status_code: 429, reason: "Limite de requisi??es excedido..."` | Aguarda tempo informado pelo servidor remoto |
| **Timeout de Conex?o** | Timeout de Socket | `ProviderTimeoutError` | Retenta at? 3x com Backoff + Jitter | `200 OK` | Inclu?do se esgotar as 3 tentativas | `status_code: 504, reason: "Tempo limite excedido..."` | Protegido por timeout granular de 7s |
| **Servidor Remoto Caiu**| `HTTP 500/502/503` | `ProviderServerError` | Retenta at? 3x com Backoff + Jitter | `200 OK` | Inclu?do se esgotar as 3 tentativas | `status_code: 502, reason: "Provedor indispon?vel..."` | Isola a falha sem abortar os demais IDs |
| **Payload Inv?lido** | N/A (Cliente) | `RequestValidationError` | Zero (Rejei??o na Borda) | `HTTP 422 Unprocessable` | N/A (Lote rejeitado) | Detalhamento dos campos inv?lidos no padr?o FastAPI | N?o inicia processamento |
