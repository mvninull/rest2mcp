# r2mcp-cli

CLI para gestao de servidores MCP via rest2mcp gateway.

## Instalacao

```bash
pipx install r2mcp-cli
```

Ou a partir do source:

```bash
pip install r2mcp-cli
```

## Uso

```bash
# Autenticar
r2mcp login

# Ver perfil
r2mcp me

# Criar servidor a partir de OpenAPI
r2mcp servers create --name "Petstore" --spec-url "https://petstore3.swagger.io/api/v3/openapi.json"

# Listar servidores
r2mcp servers list

# Ver tools disponiveis
r2mcp tools list <server_id>

# Ligar a um editor IA
r2mcp link opencode <server_id>
r2mcp link claude-code <server_id>
r2mcp link cursor <server_id>
r2mcp link vscode <server_id>

# Ver logs
r2mcp logs <server_id> --limit 20
```

## Publicacao no PyPI

```bash
cd r2mcp-cli
python prepare_build.py
python -m build
twine upload dist/*
```
