# Guia Completo: Merge de OpenAPI 3.0 com Autenticação Obrigatória

## Índice
1. [Visão Geral](#1-visão-geral)
2. [Conceitos OpenAPI 3.0 Utilizados](#2-conceitos-openapi-30-utilizados)
3. [Estrutura de Dados (Backend)](#3-estrutura-de-dados-backend)
4. [Regras de Negócio — Autenticação Obrigatória](#4-regras-de-negócio--autenticação-obrigatória)
5. [Campos do Frontend (UI/UX)](#5-campos-do-frontend-uiux)
6. [Fluxo de Implementação Passo a Passo](#6-fluxo-de-implementação-passo-a-passo)
7. [Exemplos de JSON Gerado](#7-exemplos-de-json-gerado)
8. [Diagrama de Fluxo](#8-diagrama-de-fluxo)
9. [Código de Referência](#9-código-de-referência)

---

## 1. Visão Geral

Este sistema permite **adicionar novos endpoints** a um OpenAPI Spec existente, onde cada grupo de endpoints pode ter sua **própria base URL** (`servers` ao nível do path).

### Diferencial: Segurança Obrigatória
- Se um endpoint é marcado como **privado** (requer token), o sistema **obriga** a criação de um endpoint de **autenticação** na **mesma base URL**.
- Sem rota de auth → **rotas privadas NÃO são registradas**.

### Fluxo Macro
```
OpenSpec Existente
        |
Adicionar Base URL #1 + N Rotas
        |
Tem rota privada? -> Sim -> OBRIGA rota de auth
        |
Validação passou? -> Sim -> Merge no spec
        |
Adicionar Base URL #2 + N Rotas (repete)
        |
Guardar JSON final
```

---

## 2. Conceitos OpenAPI 3.0 Utilizados

### 2.1 Servers em 3 Níveis

| Nível | Onde fica | Efeito |
|-------|-----------|--------|
| **Global** | Raiz do documento | Fallback para todos os endpoints |
| **Path** | Dentro de cada `paths/{path}` | Sobrescreve o global **apenas para esse path** |
| **Operation** | Dentro de um método HTTP | Sobrescreve path e global **apenas para esse método** |

> **Neste sistema usamos `servers` ao nível do path**, porque todos os métodos de um mesmo endpoint devem compartilhar a mesma base URL.

### 2.2 Security Schemes

```json
{
  "components": {
    "securitySchemes": {
      "bearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT"
      }
    }
  }
}
```

- `type: http` -> esquema HTTP standard
- `scheme: bearer` -> usa header `Authorization: Bearer <token>`
- `bearerFormat: JWT` -> informa que o token é um JWT (apenas documentação)

### 2.3 Security na Operação

```json
{
  "paths": {
    "/payments": {
      "post": {
        "security": [{ "bearerAuth": [] }],
        "responses": { "401": { "description": "Token inválido" } }
      }
    }
  }
}
```

- Array vazio `[]` em `bearerAuth` significa: *"requer este esquema, mas sem scopes específicos"*.
- Todo endpoint privado deve retornar `401` e `403` nas responses.

---

## 3. Estrutura de Dados (Backend)

### 3.1 Classes/Models

```python
@dataclass
class Parametro:
    nome: str              # ex: "id", "amount", "Authorization"
    local: str             # "path" | "query" | "header" | "body"
    tipo: str              # "string" | "integer" | "number" | "boolean"
    obrigatorio: bool      # True/False
    descricao: str         # Texto explicativo

@dataclass
class Rota:
    path: str              # ex: "/payments/{id}"
    metodo: str            # "get" | "post" | "put" | "delete" | "patch"
    descricao: str         # Resumo da operação
    parametros: List[Parametro]
    privada: bool          # True = requer token
    tem_body: bool         # True se tem parâmetros "body"

@dataclass
class BaseURLConfig:
    url: str               # ex: "https://payments-api.empresa.com/v2"
    rotas: List[Rota]
    tem_auth: bool         # True se tem rota de autenticação
    tem_rota_privada: bool # True se tem pelo menos uma rota privada
```

### 3.2 Estados de Validação

```
BaseURLConfig
|-- url: string
|-- rotas: Rota[]
|   |-- Rota (pública)
|   |-- Rota (privada) -> trigger: tem_rota_privada = True
|   \_ Rota (auth)    -> trigger: tem_auth = True
|-- tem_rota_privada: bool
\__ tem_auth: bool

REGRA: tem_rota_privada == True  ->  tem_auth DEVE ser True
```

---

## 4. Regras de Negócio — Autenticação Obrigatória

### 4.1 Regra Principal
> **Se uma base URL contém pelo menos uma rota privada, É OBRIGATÓRIO conter uma rota de autenticação que retorne um token JWT.**

### 4.2 Regras da Rota de Autenticação

| Campo | Valor/Requisito |
|-------|-----------------|
| **Path** | Deve ser um dos padrões: `/auth/login`, `/auth/token`, `/login`, `/token`, `/oauth/token` |
| **Método** | `POST` (recomendado) ou `GET` |
| **Retorno** | Deve retornar um objeto JSON com campo `token` (string) |
| **Base URL** | Mesma base URL das rotas privadas |
| **Parâmetros** | Tipicamente `username`/`email` + `password` no body |

### 4.3 Consequências de Violação

```
Cenário: Utilizador adiciona base URL com rota privada,
         mas NÃO adiciona rota de auth.

Resultado:
  ERRO DE VALIDAÇÃO
  -> Rotas privadas NÃO são registradas
  -> Utilizador é obrigado a criar rota de auth
  -> Só depois o merge é permitido
```

### 4.4 Cenários Válidos e Inválidos

| Cenário | Rotas | Auth | Resultado |
|---------|-------|------|-----------|
| Apenas públicas | `/users` (GET, público) | Não precisa | Merge direto |
| Privada + Auth | `/payments` (POST, privado) + `/auth/login` (POST) | Sim | Merge após validação |
| Privada SEM Auth | `/payments` (POST, privado) | Não | **BLOQUEADO** — obriga criar auth |
| Múltiplas privadas | `/payments`, `/orders` (ambos privados) + `/login` | Sim | Uma auth serve para todas |

---

## 5. Campos do Frontend (UI/UX)

### 5.1 Tela 1: Carregar OpenSpec Existente

```
+-----------------------------------------------------+
|  Carregar OpenAPI Spec Existente                    |
+-----------------------------------------------------+
|                                                     |
|  [Input File]  minha_api.json    [Escolher]         |
|                                                     |
|  Ou deixe vazio para usar um spec padrão            |
|                                                     |
|              [Carregar e Continuar]                 |
|                                                     |
+-----------------------------------------------------+
```

**Campos:**
- `file_input` (file, opcional): Ficheiro `.json` ou `.yaml` com OpenAPI 3.0
- Botão "Carregar": Lê o ficheiro e mostra preview (título, versão, quantos paths)

---

### 5.2 Tela 2: Gerenciar Base URLs (Accordion/Lista)

```
+-----------------------------------------------------+
|  Base URLs Configuradas                             |
+-----------------------------------------------------+
|                                                     |
|  +- Base URL #1 --------------------------------+  |
|  |  https://api.principal.com/v1                  |  |
|  |  2 rotas (0 privadas)                         |  |
|  |  [Editar]  [Remover]                          |  |
|  +-----------------------------------------------+  |
|                                                     |
|  +- Base URL #2 --------------------------------+  |
|  |  https://payments-api.empresa.com/v2           |  |
|  |  4 rotas (2 privadas)                         |  |
|  |  Auth: /auth/login (POST)                     |  |
|  |  [Editar]  [Remover]                          |  |
|  +-----------------------------------------------+  |
|                                                     |
|  [Adicionar Nova Base URL]                          |
|                                                     |
|              [Salvar OpenSpec Final]                |
|                                                     |
+-----------------------------------------------------+
```

---

### 5.3 Tela 3: Formulário de Base URL + Rotas

#### 5.3.1 Seção: Base URL

```
+-----------------------------------------------------+
|  Nova Base URL                                      |
+-----------------------------------------------------+
|                                                     |
|  URL Base *                                         |
|  [https://payments-api.empresa.com/v2    ]          |
|  Deve incluir protocolo (https://)                   |
|                                                     |
|  Descrição (opcional)                               |
|  [Servidor de pagamentos da empresa        ]        |
|                                                     |
|  [Adicionar Rotas para esta Base URL]               |
|                                                     |
+-----------------------------------------------------+
```

**Campos:**
| Campo | Tipo | Obrigatório | Validação |
|-------|------|-------------|-----------|
| `base_url` | text (URL) | Sim | Deve começar com `http://` ou `https://` |
| `base_description` | text | Não | Máx. 200 caracteres |

---

#### 5.3.2 Seção: Adicionar Rota (Modal ou Inline)

```
+-----------------------------------------------------+
|  Nova Rota / Endpoint                               |
+-----------------------------------------------------+
|                                                     |
|  Path *                                             |
|  [/payments/{id}                           ]        |
|  Use {param} para parâmetros de path                |
|                                                     |
|  Método HTTP *                                      |
|  [POST  ]  (GET, PUT, DELETE, PATCH)                |
|                                                     |
|  Descrição / Resumo *                               |
|  [Cria um novo pagamento                   ]        |
|                                                     |
|  Rota Privada (requer token)?                       |
|  [ ] Não  (*) Sim                                   |
|  Se sim, será obrigatório criar rota de auth        |
|                                                     |
|  --- Parâmetros ---                                 |
|                                                     |
|  [Adicionar Parâmetro]                              |
|                                                     |
|  +- Parâmetro 1 ------------------------------+     |
|  |  Nome: amount                               |     |
|  |  Local: (*) body () path () query () header |     |
|  |  Tipo:  (*) number () string () integer    |     |
|  |  Obrigatório: [x]                          |     |
|  |  [Remover]                                  |     |
|  +---------------------------------------------+     |
|                                                     |
|  +- Parâmetro 2 ------------------------------+     |
|  |  Nome: id                                   |     |
|  |  Local: () body (*) path () query () header |     |
|  |  Tipo:  () number (*) string () integer    |     |
|  |  Obrigatório: [x] (automático para path)   |     |
|  |  [Remover]                                  |     |
|  +---------------------------------------------+     |
|                                                     |
|           [Salvar Rota]  [Cancelar]                   |
|                                                     |
+-----------------------------------------------------+
```

**Campos da Rota:**
| Campo | Tipo | Obrigatório | Validação |
|-------|------|-------------|-----------|
| `route_path` | text | Sim | Deve começar com `/`. Use `{nome}` para path params |
| `route_method` | select | Sim | Um de: GET, POST, PUT, DELETE, PATCH |
| `route_description` | text | Sim | Mín. 5 caracteres |
| `route_private` | toggle/radio | Não | True/False |

**Campos do Parâmetro:**
| Campo | Tipo | Obrigatório | Validação |
|-------|------|-------------|-----------|
| `param_name` | text | Sim | Sem espaços, camelCase ou snake_case |
| `param_in` | select | Sim | Um de: path, query, header, body |
| `param_type` | select | Sim | Um de: string, integer, number, boolean |
| `param_required` | checkbox | Não | Auto-True se `param_in == path` |
| `param_description` | text | Não | Máx. 100 caracteres |

---

### 5.4 Tela 4: Rota de Autenticação Obrigatória (Modal de Bloqueio)

Quando o utilizador tenta salvar uma base URL com rotas privadas mas **sem** rota de auth:

```
+-----------------------------------------------------+
|  ATENÇÃO: AUTENTICAÇÃO OBRIGATÓRIA                  |
+-----------------------------------------------------+
|                                                     |
|  Detectamos 2 rota(s) privada(s) nesta base URL.   |
|                                                     |
|  NÃO é possível salvar sem uma rota de             |
|  autenticação que retorne o token JWT.              |
|                                                     |
|  Requisitos da rota de autenticação:               |
|     - Path: /auth/login, /login, /token, etc.       |
|     - Método: POST (recomendado)                    |
|     - Deve retornar: { "token": "jwt_aqui" }        |
|     - Parâmetros: username/email + password         |
|                                                     |
|  [Criar Rota de Autenticação Agora]                 |
|                                                     |
|  (Você NÃO pode pular esta etapa)                   |
|                                                     |
+-----------------------------------------------------+
```

**Comportamento do Frontend:**
- **Bloqueia o botão "Salvar Base URL"**
- **Abre modal** explicando a obrigatoriedade
- **Redireciona** para o formulário de rota com flag `is_auth_route=True`
- **Pré-preenche** campos sugeridos:
  - Path: `/auth/login`
  - Método: `POST`
  - Parâmetros: `username` (body, string), `password` (body, string)

---

### 5.5 Tela 5: Preview e Validação Final

```
+-----------------------------------------------------+
|  Preview do OpenSpec Final                          |
+-----------------------------------------------------+
|                                                     |
|  Estatísticas:                                      |
|     - Total de paths: 7                             |
|     - Rotas privadas: 2                             |
|     - SecuritySchemes: bearerAuth (JWT)             |
|     - Base URLs distintas: 2                        |
|                                                     |
|  Endpoints:                                         |
|     /users (GET) -> global                          |
|     /products (POST) -> global                      |
|     /payments (POST) -> https://payments-api...     |
|     /payments/{id} (GET) -> https://payments...     |
|     /auth/login (POST) -> https://payments...       |
|                                                     |
|  [Ver JSON Completo]  [Download]                    |
|                                                     |
|              [Salvar em Ficheiro]                     |
|                                                     |
+-----------------------------------------------------+
```

---

## 6. Fluxo de Implementação Passo a Passo

### Passo 1: Inicialização
```
1. Carregar ficheiro OpenSpec existente (JSON/YAML)
2. Se não existir, criar estrutura padrão:
   {
     "openapi": "3.0.0",
     "info": { "title": "...", "version": "1.0.0" },
     "servers": [...],
     "paths": {}
   }
3. Guardar em memória (nunca mutar o original diretamente)
```

### Passo 2: Loop de Base URLs
```
ENQUANTO utilizador quiser adicionar base URLs:

  2.1 Coletar URL base
      -> Input: "https://api.exemplo.com/v2"
      -> Validar: deve ter protocolo http/https

  2.2 Loop de Rotas (infinito até cancelar)
      -> Para cada rota:
          a. Coletar path, método, descrição
          b. Perguntar: "É privada?" (toggle)
          c. Se privada -> marcar flag `tem_rota_privada = True`
          d. Coletar N parâmetros (nome, local, tipo, obrigatório)
          e. Adicionar à lista de rotas

  2.3 Validação de Segurança
      -> SE `tem_rota_privada == True` E `tem_auth == False`:
          a. EXIBIR ERRO BLOQUEANTE
          b. FORÇAR criação de rota de auth
          c. Só prosseguir quando `tem_auth == True`

  2.4 Merge na memória
      -> Chamar `merge_routes_into_openspec(spec, config)`
      -> Adicionar `servers` ao nível do path
      -> Adicionar `security` se rota for privada
      -> Adicionar `securitySchemes` no `components` (só uma vez)
```

### Passo 3: Finalização
```
3.1 Mostrar preview com estatísticas
3.2 Permitir download do JSON
3.3 Salvar em ficheiro `.json`
```

---

## 7. Exemplos de JSON Gerado

### 7.1 Exemplo Completo: API com Endpoints Públicos e Privados

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "API Principal",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "https://api.principal.com/v1",
      "description": "Servidor principal"
    }
  ],
  "components": {
    "securitySchemes": {
      "bearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Token JWT obtido no endpoint de autenticação"
      }
    }
  },
  "paths": {
    "/users": {
      "get": {
        "summary": "Lista utilizadores",
        "responses": {
          "200": { "description": "OK" }
        }
      }
    },
    "/auth/login": {
      "servers": [
        {
          "url": "https://payments-api.empresa.com/v2",
          "description": "Base URL para /auth/login"
        }
      ],
      "post": {
        "summary": "Autenticação - retorna token JWT",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "username": { "type": "string" },
                  "password": { "type": "string" }
                },
                "required": ["username", "password"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Login bem-sucedido",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "token": {
                      "type": "string",
                      "description": "JWT token para rotas privadas"
                    }
                  }
                }
              }
            }
          },
          "401": { "description": "Credenciais inválidas" }
        }
      }
    },
    "/payments": {
      "servers": [
        {
          "url": "https://payments-api.empresa.com/v2",
          "description": "Base URL para /payments"
        }
      ],
      "post": {
        "summary": "Cria um pagamento (PRIVADO)",
        "security": [
          {
            "bearerAuth": []
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "amount": { "type": "number" },
                  "currency": { "type": "string" }
                }
              }
            }
          }
        },
        "responses": {
          "201": { "description": "Pagamento criado" },
          "401": { "description": "Não autorizado. Envie: Authorization: Bearer <token>" },
          "403": { "description": "Proibido - Sem permissões suficientes" }
        }
      }
    },
    "/payments/{id}": {
      "servers": [
        {
          "url": "https://payments-api.empresa.com/v2",
          "description": "Base URL para /payments/{id}"
        }
      ],
      "get": {
        "summary": "Obtém pagamento por ID (PRIVADO)",
        "security": [
          {
            "bearerAuth": []
          }
        ],
        "parameters": [
          {
            "name": "id",
            "in": "path",
            "required": true,
            "schema": { "type": "string" },
            "description": "Identificador do pagamento"
          }
        ],
        "responses": {
          "200": { "description": "OK" },
          "401": { "description": "Não autorizado" },
          "404": { "description": "Pagamento não encontrado" }
        }
      }
    }
  }
}
```

### 7.2 Destaques do JSON

| Elemento | Significado |
|----------|-------------|
| `paths./payments.servers` | Sobrescreve o servidor global **apenas** para `/payments` |
| `paths./payments.post.security` | Exige `Authorization: Bearer <token>` |
| `components.securitySchemes.bearerAuth` | Define o esquema de autenticação (uma vez no doc) |
| `paths./auth.login` | **Obrigatória** quando existem rotas privadas |
| `responses.401` | Documenta erro de autenticação |

---

## 8. Diagrama de Fluxo

```
+-------------+
|   INICIO    |
+------+------+
       |
       v
+---------------+
| Carregar Spec |
| (JSON/YAML)   |
+-------+-------+
        |
        v
+---------------+     Não
| Quer adicionar|---------------------------+
| base URL?     |                           |
+-------+-------+                           |
        | Sim                             |
        v                                 |
+---------------+                         |
| Inserir URL   |                         |
| Base          |                         |
+-------+-------+                         |
        |                                 |
        v                                 |
+---------------+                         |
| Adicionar     |<--------------+         |
| rotas (loop)  |               |         |
+-------+-------+               |         |
        |                       |         |
        v                       |         |
+---------------+    Não        |         |
| Mais rotas?   |---------------+         |
+-------+-------+                         |
        | Sim                           |
        v                                 |
+---------------+                         |
| Definir path, |                         |
| método, params|                         |
+-------+-------+                         |
        |                                 |
        v                                 |
+---------------+                         |
| É rota        |--Sim--+                 |
| privada?      |       |                 |
+-------+-------+       |                 |
        | Não         |                 |
        |             v                 |
        |    +---------------+          |
        |    | tem_rota_     |          |
        |    | privada=True  |          |
        |    +-------+-------+          |
        |            |                 |
        +------------+-----------------+
                     |
                     v
            +---------------+
            | Validar:      |---Não---+
            | existe auth?  |         |
            +-------+-------+         |
                    | Sim            |
                    |                v
                    |       +---------------+
                    |       | ERRO          |
                    |       | BLOQUEANTE    |
                    |       +-------+-------+
                    |               |
                    |               v
                    |       +---------------+
                    |       | Forçar criação|
                    |       | de /auth/login|
                    |       +---------------+
                    |
                    v
            +---------------+
            | Merge no spec |
            | (deep copy)   |
            +-------+-------+
                    |
                    +-------------------> (volta ao inicio)
```

---

## 9. Código de Referência

### 9.1 Função de Merge (Python)

```python
import copy
from typing import List, Dict, Any

def merge_routes_into_openspec(openspec: dict, config: BaseURLConfig) -> dict:
    result = copy.deepcopy(openspec)

    # 1. Adicionar securitySchemes se há rotas privadas
    if config.tem_rota_privada:
        if "components" not in result:
            result["components"] = {}
        if "securitySchemes" not in result["components"]:
            result["components"]["securitySchemes"] = {}

        if "bearerAuth" not in result["components"]["securitySchemes"]:
            result["components"]["securitySchemes"]["bearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Token JWT obtido no endpoint de autenticação"
            }

    # 2. Processar cada rota
    for rota in config.rotas:
        path = rota.path
        method = rota.metodo.lower()

        operation = {
            "summary": rota.descricao,
            "responses": {
                "200": {"description": "OK"},
                "401": {"description": "Não autorizado"}
            }
        }

        # Parâmetros
        params_normais = [p for p in rota.parametros if p.local != "body"]
        if params_normais:
            operation["parameters"] = [
                {
                    "name": p.nome,
                    "in": p.local,
                    "required": p.obrigatorio,
                    "schema": {"type": p.tipo},
                    "description": p.descricao
                }
                for p in params_normais
            ]

        # RequestBody
        params_body = [p for p in rota.parametros if p.local == "body"]
        if params_body:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                p.nome: {"type": p.tipo} for p in params_body
                            }
                        }
                    }
                }
            }

        # Segurança
        if rota.privada:
            operation["security"] = [{"bearerAuth": []}]

        # Criar/atualizar path
        if path not in result["paths"]:
            result["paths"][path] = {
                "servers": [{"url": config.url}]
            }
        else:
            if "servers" not in result["paths"][path]:
                result["paths"][path]["servers"] = [{"url": config.url}]

        result["paths"][path][method] = operation

    return result
```

### 9.2 Validação Obrigatória (Python)

```python
def validar_autenticacao(config: BaseURLConfig) -> tuple[bool, str]:
    if not config.tem_rota_privada:
        return True, ""

    auth_paths = ["/auth/login", "/auth/token", "/login", "/token", "/oauth/token"]

    tem_rota_auth = any(
        r.path in auth_paths and r.metodo.lower() in ["post", "get"]
        for r in config.rotas
    )

    if not tem_rota_auth:
        return False, (
            f"Base URL {config.url} tem rotas privadas mas "
            f"não tem rota de autenticação. "
            f"Adicione uma rota em: {', '.join(auth_paths)}"
        )

    config.tem_auth = True
    return True, ""
```

### 9.3 Estrutura TypeScript (Frontend)

```typescript
// Types para o frontend
interface Parametro {
  nome: string;
  local: 'path' | 'query' | 'header' | 'body';
  tipo: 'string' | 'integer' | 'number' | 'boolean';
  obrigatorio: boolean;
  descricao?: string;
}

interface Rota {
  path: string;
  metodo: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  descricao: string;
  parametros: Parametro[];
  privada: boolean;
}

interface BaseURLConfig {
  url: string;
  descricao?: string;
  rotas: Rota[];
  temAuth: boolean;
  temRotaPrivada: boolean;
}

// Validação no frontend
function validarBaseURL(config: BaseURLConfig): string | null {
  const temPrivada = config.rotas.some(r => r.privada);
  const authPaths = ['/auth/login', '/auth/token', '/login', '/token', '/oauth/token'];
  const temAuth = config.rotas.some(r => 
    authPaths.includes(r.path) && ['POST', 'GET'].includes(r.metodo)
  );

  if (temPrivada && !temAuth) {
    return `Rota de autenticação obrigatória!`;
  }

  return null;
}
```

---

## Checklist de Implementação

### Backend
- [ ] Ler OpenSpec de ficheiro JSON/YAML
- [ ] Estrutura `BaseURLConfig` com flags `tem_auth` e `tem_rota_privada`
- [ ] Loop infinito para adicionar N base URLs
- [ ] Loop infinito para adicionar N rotas por base URL
- [ ] Loop infinito para adicionar N parâmetros por rota
- [ ] **Validação obrigatória**: se privada -> deve ter auth
- [ ] Forçar criação de rota de auth (não permitir cancelar)
- [ ] Merge com `copy.deepcopy()` (preservar original)
- [ ] Injetar `servers` ao nível do path
- [ ] Injetar `securitySchemes` no `components` (uma vez)
- [ ] Injetar `security` nas operações privadas
- [ ] Guardar JSON final formatado

### Frontend
- [ ] Input de ficheiro para carregar spec
- [ ] Lista/accordion de base URLs adicionadas
- [ ] Formulário de base URL (URL + descrição)
- [ ] Formulário de rota (path, método, descrição, toggle privada)
- [ ] Sub-formulário de parâmetros (nome, local, tipo, obrigatório)
- [ ] **Modal bloqueante** quando falta rota de auth
- [ ] Formulário pré-preenchido para rota de auth
- [ ] Preview do JSON com syntax highlighting
- [ ] Download do ficheiro `.json`

---

*Documento gerado para implementação de Merge OpenAPI 3.0 com Autenticação Obrigatória.*
