# MCP Server Store — Problema e Soluções

## O Problema

A loja de servidores MCP (via Glama API) lista centenas de servidores, mas **não fornece informação suficiente para os instalar automaticamente**.

### Dados disponíveis por servidor (Glama API)

```json
{
  "id": "m763qg3zzq",
  "name": "mcp-mychem",
  "namespace": "pipeworx-io",
  "slug": "mcp-mychem",
  "repository": { "url": "https://github.com/pipeworx-io/mcp-mychem" },
  "attributes": ["hosting:remote-capable"],
  "environmentVariablesJsonSchema": { ... },
  "tools": []
}
```

**O que falta**: a Glama **não devolve**:
- O nome do pacote npm / PyPI / etc.
- O runtime necessário (`npx`, `uvx`, `pipx`, docker, etc.)
- O comando de instalação
- Se o servidor é executável (tem `bin` field)
- Se está publicado em algum registo

### Consequência

O `Quick Select` (Excel, File System, SQLite, PDF) funciona porque os packages são **conhecidos e verificados manualmente** (`@modelcontextprotocol/server-filesystem`, `mcp-excel-server`, etc.).

A loja tenta adivinhar o nome do package a partir de `namespace` e `slug`:
- `namespace = "pipeworx-io"`, `slug = "mcp-mychem"` → `@pipeworx-io/mcp-mychem`
- Mas este package **não existe no npm** (404)
- O package real podia ser `@pipeworx/mcp-mychem` (outro scope), `mcp-server-demo` (sem scope), ou simplesmente não estar publicado

### Resultado

O merge cria o servidor, mas o subprocesso (`npx`) falha porque o package não existe → `Connection closed` durante `list_tools`.

---

## Soluções Implementadas

### 1. Prefixo `@` para packages scoped do npm

**Antes**: `namespace/slug` → `modelcontextprotocol/server-filesystem` (faltava `@`)
**Depois**: `@namespace/slug` → `@modelcontextprotocol/server-filesystem` ✅

### 2. Verificação de existência no npm (`/v1/store/check-package`)

Endpoint que recebe `name`, `namespace`, `slug`, `repo_url` e tenta, por ordem:

1. **npm registry**: `HEAD https://registry.npmjs.org/@namespace/slug`
   - Se existe → `npx @namespace/slug`

2. **GitHub `package.json`**: lê o ficheiro do repositório
   - Obtém o `name` real do package
   - Verifica se esse nome existe **no npm publicado**
   - Se sim, verifica se a **última versão publicada tem `bin` field**
   - Se tem bin → `npx nome_real` (ex: `mcp-server-demo` em vez de `@therobertmack/mcp-server-demo`)

3. **`pyproject.toml`** / **`setup.py`** (Python):
   - Se existe → `uvx nome_python` ou `pipx nome_python`

4. **Fallback GitHub**: `npx github:owner/repo`

### 3. Frontend atualiza Config JSON automaticamente

Quando o endpoint retorna um comando válido (`data.command` + `data.args`), o Config JSON na textarea é atualizado com o runtime correto.

---

## Limitações Atuais

- **Muitos servidores na Glama não estão publicados** em nenhum registo (npm, PyPI)
- Alguns precisam de compilação (TypeScript → JavaScript) antes de executar
- Outros usam Docker ou setups manuais
- A Glama não fornece um campo `installCommand` ou `runtime`

## Testado

| Servidor | Resultado |
|---|---|
| `@modelcontextprotocol/server-filesystem` ✅ | Existe no npm, funciona |
| `@pipeworx-io/mcp-mychem` ❌ | Não existe no npm, package.json sem bin, fallback GitHub falha |
| `mcp-server-demo` (therobertmack) ❌ | Existe no npm com bin, mas endpoint precisa de usar o nome sem scope |

## Próximos Passos (se aplicável)

- Adicionar `uvx`/`pipx` como runtime primário quando o GitHub repo tiver `pyproject.toml`
- Exibir aviso claro quando nenhum comando funcionar
- (Opcional) Tentar correr `npx github:owner/repo` com `--entrypoint` apontando para `main` do `package.json`
