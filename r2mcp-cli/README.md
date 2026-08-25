# r2mcp

CLI para gestão de servidores MCP via rest2mcp gateway.

## Instalação

Requer Python 3.10+ e pipx.

```bash
pipx install r2mcp
```

## Uso

```bash
r2mcp login
r2mcp servers create --name my-api --spec-url https://example.com/openapi.json
r2mcp tools list <server_id>
r2mcp --help
```

## Desenvolvimento

```bash
python prepare_build.py
python -m build
```